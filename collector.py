"""YouTube 收集模組：搜尋關鍵字、補齊影片詳情、寫入資料庫。

配額說明：search.list 每次 100 單位、videos.list 每次 1 單位。
11 個關鍵字每天跑 1 次約 1,111 單位，遠低於每日 10,000 免費配額。
"""
import logging
import re

import requests

import db

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"

log = logging.getLogger(__name__)

_DURATION_RE = re.compile(r"PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?")


def _safe_err(e):
    """遮蔽錯誤訊息中的 API 金鑰（YouTube API 金鑰必須放在網址參數，錯誤訊息會帶出完整網址）。"""
    return re.sub(r"key=[^&\s]+", "key=***", str(e))


def parse_duration(iso):
    m = _DURATION_RE.fullmatch(iso or "")
    if not m or not any(m.groups()):
        return 0
    return (
        int(m.group("h") or 0) * 3600
        + int(m.group("m") or 0) * 60
        + int(m.group("s") or 0)
    )


def search_videos(api_key, keyword, published_after, language="zh-Hant", max_results=25):
    params = {
        "part": "id",
        "q": keyword,
        "type": "video",
        "order": "date",
        "publishedAfter": published_after,
        "relevanceLanguage": language,
        "maxResults": max_results,
        "key": api_key,
    }
    resp = requests.get(SEARCH_URL, params=params, timeout=30)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]


def fetch_video_details(api_key, video_ids):
    videos = []
    for i in range(0, len(video_ids), 50):  # videos.list 一次最多 50 部
        chunk = video_ids[i:i + 50]
        params = {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(chunk),
            "key": api_key,
        }
        try:
            resp = requests.get(VIDEOS_URL, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            # 換成遮蔽金鑰後的訊息再往上拋，避免呼叫端把原始網址寫進 log
            raise RuntimeError(f"影片詳情查詢失敗：{_safe_err(e)}") from None
        for it in resp.json().get("items", []):
            sn = it.get("snippet", {})
            videos.append({
                "video_id": it["id"],
                "title": sn.get("title", ""),
                "channel": sn.get("channelTitle", ""),
                "description": sn.get("description", "")[:1000],
                "published_at": sn.get("publishedAt", ""),
                "thumbnail_url": sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
                "duration_seconds": parse_duration(it.get("contentDetails", {}).get("duration", "")),
                "view_count": int(it.get("statistics", {}).get("viewCount", 0)),
            })
    return videos


def fetch_channel_video_ids(api_key, handle, max_results=25):
    """抓取指定頻道（handle，如 @sensebar）最新上傳的影片 ID。

    每頻道僅花 2 個配額單位（channels.list + playlistItems.list），
    不經 publishedAfter 過濾——靠 video_id 去重避免重複入庫。
    """
    params = {"part": "contentDetails", "forHandle": handle, "key": api_key}
    resp = requests.get(CHANNELS_URL, params=params, timeout=30)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        log.warning("找不到頻道：%s", handle)
        return []
    uploads = (
        items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    )
    if not uploads:
        log.warning("頻道 %s 缺少上傳清單資訊，略過", handle)
        return []

    params = {
        "part": "contentDetails",
        "playlistId": uploads,
        "maxResults": max_results,
        "key": api_key,
    }
    resp = requests.get(PLAYLIST_ITEMS_URL, params=params, timeout=30)
    resp.raise_for_status()
    return [
        it["contentDetails"]["videoId"]
        for it in resp.json().get("items", [])
        if it.get("contentDetails", {}).get("videoId")
    ]


def collect(conn, api_key, keywords, published_after,
            min_duration=120, language="zh-Hant", max_results=25, channels=(), extra_ids=()):
    """搜尋所有關鍵字並寫入新影片，回傳新增數。單一關鍵字失敗不中斷整體。

    若所有關鍵字皆搜尋失敗，會擲出 RuntimeError，避免呼叫端誤以為本次收集
    成功而推進 last_collect_at，造成這段期間的影片被永久跳過。

    人工提交的影片（extra_ids）不套用時長過濾（人工判斷優先於自動規則）。
    """
    candidate_ids = []
    success_count = 0
    for kw in keywords:
        try:
            ids = search_videos(api_key, kw, published_after, language, max_results)
        except requests.RequestException as e:
            log.warning("關鍵字「%s」搜尋失敗：%s", kw, _safe_err(e))
            continue
        success_count += 1
        candidate_ids.extend(i for i in ids if not db.video_exists(conn, i))

    for ch in channels:
        try:
            ids = fetch_channel_video_ids(api_key, ch, max_results)
        except (requests.RequestException, KeyError, IndexError) as e:
            log.warning("頻道「%s」抓取失敗：%s", ch, _safe_err(e))
            continue
        candidate_ids.extend(i for i in ids if not db.video_exists(conn, i))

    unique_ids = list(dict.fromkeys(candidate_ids))  # 去重且保序

    # 人工提交的影片：不套用時長過濾（人工判斷優先於自動規則）。
    # 排除已在搜尋結果中的，避免重複查詳情與重複計數。
    already = set(unique_ids)
    submitted = [i for i in dict.fromkeys(extra_ids)
                 if i not in already and not db.video_exists(conn, i)]

    added = 0
    for v in fetch_video_details(api_key, unique_ids):
        if v["duration_seconds"] < min_duration:
            continue
        db.insert_video(conn, v)
        added += 1

    for v in fetch_video_details(api_key, submitted):
        db.insert_video(conn, v)
        added += 1

    # 放在寫入之後才擲出：頻道影片已保住，僅阻止呼叫端推進 last_collect_at
    if keywords and success_count == 0:
        raise RuntimeError("所有關鍵字搜尋皆失敗，本次不推進 last_collect_at")
    return added
