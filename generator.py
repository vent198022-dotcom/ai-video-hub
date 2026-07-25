"""靜態網站資料產生模組：從資料庫產出 docs/videos.json。"""
import json
from datetime import datetime, timezone
from pathlib import Path

import db


def generate(conn, site_dir):
    """產出 videos.json，回傳上架影片數。"""
    site = Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)
    videos = db.get_site_videos(conn)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(videos),
        "videos": videos,
    }
    (site / "videos.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return len(videos)
