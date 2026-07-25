"""一次性回補腳本：補收近一年的影片。

用法：python backfill.py
- 關鍵字：每組往回翻頁最多 MAX_SEARCH_PAGES 頁（每頁 50 筆、100 配額單位）
- 頻道：沿上傳清單往回翻頁，直到影片發佈日早於截止日（每頁 50 筆、1 配額單位）
收集完成後請執行 python main.py 進行分類與發佈（分類量大時會分多天自動消化）。
"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

import collector
import db

ROOT = Path(__file__).parent
BACKFILL_DAYS = 365
MAX_SEARCH_PAGES = 3   # 每組關鍵字最多翻 3 頁（150 部），控制配額
MAX_CHANNEL_PAGES = 10

log = logging.getLogger("backfill")


def _utc_iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def search_page(api_key, keyword, published_after, language, page_token=None):
    """搜尋單頁（50 筆），回傳 (影片ID清單, 下一頁token)。"""
    params = {
        "part": "id",
        "q": keyword,
        "type": "video",
        "order": "date",
        "publishedAfter": published_after,
        "relevanceLanguage": language,
        "maxResults": 50,
        "key": api_key,
    }
    if page_token:
        params["pageToken"] = page_token
    resp = requests.get(collector.SEARCH_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    ids = [it["id"]["videoId"] for it in data.get("items", [])
           if it.get("id", {}).get("videoId")]
    return ids, data.get("nextPageToken")


def backfill_keywords(api_key, keywords, published_after, language,
                      max_pages=MAX_SEARCH_PAGES):
    """所有關鍵字翻頁搜尋。回傳 (影片ID清單, 消耗配額單位)。"""
    all_ids = []
    used = 0
    for kw in keywords:
        token = None
        for page in range(max_pages):
            try:
                ids, token = search_page(api_key, kw, published_after, language, token)
            except requests.RequestException as e:
                log.warning("關鍵字「%s」第 %d 頁搜尋失敗：%s",
                            kw, page + 1, collector._safe_err(e))
                break
            used += 100
            all_ids.extend(ids)
            log.info("關鍵字「%s」第 %d 頁：%d 部", kw, page + 1, len(ids))
            if not token:
                break
    return all_ids, used


def backfill_channel(api_key, handle, cutoff_iso, max_pages=MAX_CHANNEL_PAGES):
    """沿頻道上傳清單往回翻頁，抓到發佈日早於截止日為止。回傳 (ID清單, 配額)。"""
    params = {"part": "contentDetails", "forHandle": handle, "key": api_key}
    resp = requests.get(collector.CHANNELS_URL, params=params, timeout=30)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    uploads = (
        items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        if items else None
    )
    if not uploads:
        log.warning("頻道 %s 查無上傳清單，略過", handle)
        return [], 1

    ids = []
    used = 1
    token = None
    for _ in range(max_pages):
        params = {
            "part": "contentDetails",
            "playlistId": uploads,
            "maxResults": 50,
            "key": api_key,
        }
        if token:
            params["pageToken"] = token
        resp = requests.get(collector.PLAYLIST_ITEMS_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        used += 1
        reached_cutoff = False
        for it in data.get("items", []):
            cd = it.get("contentDetails", {})
            vid = cd.get("videoId")
            published = cd.get("videoPublishedAt", "")
            if not vid:
                continue
            if published and published < cutoff_iso:
                reached_cutoff = True
                break
            ids.append(vid)
        token = data.get("nextPageToken")
        if reached_cutoff or not token:
            break
    log.info("頻道 %s：回補 %d 部", handle, len(ids))
    return ids, used


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        log.error("缺少 YOUTUBE_API_KEY，請檢查 .env")
        return 1

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    conn = db.connect(ROOT / "videos.db")
    cutoff = _utc_iso(datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS))
    log.info("回補範圍：%s 之後發佈的影片", cutoff)

    kw_ids, used_kw = backfill_keywords(
        api_key, cfg["keywords"], cutoff, cfg["filters"]["relevance_language"])
    ch_ids = []
    used_ch = 0
    for ch in cfg.get("channels") or []:
        try:
            ids, used = backfill_channel(api_key, ch, cutoff)
        except (requests.RequestException, KeyError, IndexError) as e:
            log.warning("頻道「%s」回補失敗：%s", ch, collector._safe_err(e))
            continue
        ch_ids.extend(ids)
        used_ch += used

    candidates = [i for i in dict.fromkeys(kw_ids + ch_ids)
                  if not db.video_exists(conn, i)]
    log.info("去重後新影片候選：%d 部", len(candidates))

    added = 0
    min_duration = cfg["filters"]["min_duration_seconds"]
    # 每 50 部一批查詳情、隨查隨寫，單批失敗只損失該批，已寫入的不受影響
    for i in range(0, len(candidates), 50):
        chunk = candidates[i:i + 50]
        try:
            details = collector.fetch_video_details(api_key, chunk)
        except RuntimeError as e:
            log.warning("第 %d 批影片詳情查詢失敗，略過該批：%s", i // 50 + 1, e)
            continue
        for v in details:
            if v["duration_seconds"] < min_duration:
                continue
            db.insert_video(conn, v)
            added += 1

    details_units = (len(candidates) + 49) // 50
    log.info("回補完成：新增 %d 部待分類；YouTube 配額約消耗 %d 單位",
             added, used_kw + used_ch + details_units)
    log.info("請執行 python main.py 進行分類與發佈")
    return 0


if __name__ == "__main__":
    sys.exit(main())
