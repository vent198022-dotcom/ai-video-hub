"""失效影片清理：偵測已下架或轉為非公開的影片，從網站移除。

安全原則：任何一批查詢失敗就跳過該批，寧可漏刪也不可誤刪。
"""
import logging

import requests

import collector
import db

log = logging.getLogger(__name__)


def remove_dead_videos(conn, api_key):
    """檢查所有上架影片是否仍公開可看，標記失效者。回傳標記筆數。"""
    live_ids = [v["video_id"] for v in db.get_site_videos(conn)]
    if not live_ids:
        return 0

    dead = []
    for i in range(0, len(live_ids), 50):
        chunk = live_ids[i:i + 50]
        params = {"part": "status", "id": ",".join(chunk), "key": api_key}
        try:
            resp = requests.get(collector.VIDEOS_URL, params=params, timeout=30)
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except requests.RequestException as e:
            log.warning("第 %d 批失效檢查失敗，略過該批：%s",
                        i // 50 + 1, collector._safe_err(e))
            continue
        public = {
            it["id"] for it in items
            if it.get("status", {}).get("privacyStatus") == "public"
        }
        dead.extend(vid for vid in chunk if vid not in public)

    if dead:
        log.info("偵測到 %d 部影片已失效，從網站移除", len(dead))
    return db.mark_removed(conn, dead)
