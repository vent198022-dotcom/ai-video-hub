"""管線入口：收集 → 分類 → 產頁 → 發佈。由 Windows 工作排程器每天呼叫一次。"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

import classifier
import collector
import db
import generator
import publisher

ROOT = Path(__file__).parent


def _setup_logging():
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "run.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def _utc_iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main():
    _setup_logging()
    log = logging.getLogger("main")

    load_dotenv(ROOT / ".env")
    yt_key = os.environ.get("YOUTUBE_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not yt_key or not gemini_key:
        log.error("缺少 YOUTUBE_API_KEY 或 GEMINI_API_KEY，請檢查 .env")
        return 1

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    conn = db.connect(ROOT / "videos.db")

    now = datetime.now(timezone.utc)
    published_after = db.get_meta(conn, "last_collect_at") or _utc_iso(
        now - timedelta(days=cfg["filters"]["initial_days"])
    )

    try:
        added = collector.collect(
            conn, yt_key, cfg["keywords"], published_after,
            min_duration=cfg["filters"]["min_duration_seconds"],
            language=cfg["filters"]["relevance_language"],
            max_results=cfg["filters"]["max_results_per_keyword"],
        )
        db.set_meta(conn, "last_collect_at", _utc_iso(now))
        log.info("收集完成：新增 %d 部影片", added)
    except Exception:
        log.exception("收集階段失敗，繼續處理既有待分類影片")

    ok, skip, fail = classifier.classify_pending(
        conn, gemini_key, cfg["gemini"]["model"], cfg["categories"],
        batch_size=cfg["gemini"]["batch_size"],
    )
    log.info("分類完成：上架 %d、排除 %d、失敗待重試 %d", ok, skip, fail)

    count = generator.generate(conn, ROOT / "docs")
    log.info("網頁資料已產出：共 %d 部影片", count)

    try:
        if publisher.publish(str(ROOT)):
            log.info("已推送至 GitHub，網站將於約 1 分鐘內更新")
        else:
            log.info("無變更，略過發佈")
    except Exception:
        log.exception("發佈階段失敗（資料已存檔，下次執行會一併推送）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
