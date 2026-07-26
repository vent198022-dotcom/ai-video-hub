"""管線入口：收集 → 分類 → 產頁 → 發佈。由 Windows 工作排程器每天呼叫一次。"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

import article
import classifier
import cleanup
import collector
import db
import generator
import github
import publisher
import sites
import submissions
import transcript

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

    submitted_articles = []
    try:
        submitted_videos, submitted_articles = submissions.read_entries(
            ROOT / "submit.txt")
        if submitted_videos or submitted_articles:
            log.info("讀到手動提交：影片 %d 筆、文章 %d 筆",
                     len(submitted_videos), len(submitted_articles))
        added = collector.collect(
            conn, yt_key, cfg["keywords"], published_after,
            min_duration=cfg["filters"]["min_duration_seconds"],
            language=cfg["filters"]["relevance_language"],
            max_results=cfg["filters"]["max_results_per_keyword"],
            channels=cfg.get("channels") or [],
            extra_ids=submitted_videos,
        )
        db.set_meta(conn, "last_collect_at", _utc_iso(now))
        log.info("收集完成：新增 %d 部影片", added)
    except Exception:
        log.exception("收集階段失敗，繼續處理既有待分類影片")

    site_urls = []
    try:
        site_list = cfg.get("sites") or []
        if site_list:
            sf = cfg.get("site_filter") or {}
            kw = sf.get("match") or []
            cap = sf.get("max_per_site", 20)
            for site in site_list:
                site_urls.extend(sites.discover(site, kw, cap))
            if site_urls:
                log.info("網站訂閱共發現 %d 篇候選文章", len(site_urls))
    except Exception:
        log.exception("網站訂閱階段失敗，略過本次訂閱")

    repo_items = []
    try:
        gcfg = cfg.get("github") or {}
        if gcfg.get("enabled"):
            gh_token = os.environ.get("GITHUB_TOKEN")
            if not gh_token:
                log.warning("缺少 GITHUB_TOKEN，略過 GitHub 收集")
            else:
                repo_items = github.discover(
                    gh_token, gcfg.get("queries") or [],
                    gcfg.get("min_stars", 2000), gcfg.get("pushed_days", 180),
                    per_query=gcfg.get("per_query", 20),
                )
                log.info("GitHub 發現 %d 個候選專案", len(repo_items))
    except Exception:
        log.exception("GitHub 收集階段失敗，略過本次收集")

    repo_added = 0
    try:
        for item in repo_items:
            if db.video_exists(conn, item["video_id"]):
                continue
            db.insert_video(conn, item)
            repo_added += 1
    except Exception:
        log.exception("專案寫入階段失敗，已寫入的不受影響")
    if repo_added:
        log.info("開源專案收集完成：新增 %d 個", repo_added)

    art_max = (cfg.get("article") or {}).get("max_chars", 3000)
    art_added = 0
    try:
        for url in dict.fromkeys(list(submitted_articles) + site_urls):
            if db.video_exists(conn, article.make_id(url)):
                continue
            item = article.fetch(url, art_max)
            if item is None:
                continue          # article.fetch 已記錄原因
            db.insert_video(conn, item)
            art_added += 1
    except Exception:
        log.exception("文章收集階段失敗，已寫入的文章不受影響")
    if art_added:
        log.info("文章收集完成：新增 %d 篇", art_added)

    tcfg = cfg.get("transcript") or {}
    use_transcript = bool(tcfg.get("enabled"))
    batch_size = (tcfg.get("batch_size", 5) if use_transcript
                  else cfg["gemini"]["batch_size"])
    transcript_fn = (
        (lambda vid: transcript.fetch(vid, tcfg.get("max_chars", 3000)))
        if use_transcript else None
    )
    ok, skip, fail = classifier.classify_pending(
        conn, gemini_key, cfg["gemini"]["model"], cfg["categories"],
        batch_size=batch_size,
        pause_seconds=cfg["gemini"].get("pause_seconds", 6),
        transcript_fn=transcript_fn,
    )
    log.info("分類完成：上架 %d、排除 %d、失敗待重試 %d", ok, skip, fail)

    try:
        removed = cleanup.remove_dead_videos(conn, yt_key)
        if removed:
            log.info("失效清理：移除 %d 部影片", removed)
    except Exception:
        log.exception("失效清理階段失敗，略過本次清理")

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
