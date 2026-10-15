"""一次性清理腳本：把資料庫裡既有的影片套用標題過濾。

用法：
    python apply_title_filter.py --dry-run
        只列出會被排除的筆數與範例，不改資料庫。
    python apply_title_filter.py
        實際標記為 excluded；網站要等下次 main.py 發佈後才會更新。

- 待分類／待重試（pending、failed）：非中文、日文、廣東話三種規則都套用
- 已上架（classified）：只依廣東話規則下架；非中文、日文規則對已上架影片
  誤判風險較高（例如中文影片標題夾一段日文頻道名），維持上架
- 只處理影片；文章與開源專案不受影響
- submit.txt 裡人工提交的影片不動（人工判斷優先於自動規則）
- 只改狀態、保留分類與摘要，日後可把狀態改回 classified 救回
"""
import argparse
import collections
import logging
import sys
from pathlib import Path

import db
import submissions
import title_filter

ROOT = Path(__file__).parent

log = logging.getLogger(__name__)


def apply(conn, protected_ids=(), dry_run=False):
    """套用標題過濾，回傳 {video_id: (原狀態, 原因)}。dry_run 時不改資料庫。"""
    protected = set(protected_ids)
    found = {}
    rows = conn.execute(
        "SELECT video_id, title, status FROM videos"
        " WHERE coalesce(content_type, 'video') = 'video'"
        " AND status IN ('pending', 'failed', 'classified')"
    ).fetchall()
    for vid, title, status in rows:
        if vid in protected:
            continue
        reason = title_filter.reject_reason(title)
        if reason is None or (status == "classified" and reason != "廣東話"):
            continue
        found[vid] = (status, reason)
    if not dry_run:
        db.exclude_items(conn, list(found))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description="對既有影片套用標題過濾")
    parser.add_argument("--dry-run", action="store_true", help="只列出結果，不改資料庫")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    conn = db.connect(ROOT / "videos.db")
    protected = submissions.read_entries(ROOT / "submit.txt")[0]
    found = apply(conn, protected, dry_run=args.dry_run)

    summary = collections.Counter(found.values())
    titles = dict(conn.execute("SELECT video_id, title FROM videos"))
    for (status, reason), n in sorted(summary.items()):
        log.info("%s｜%s：%d 筆", status, reason, n)
        for vid in [v for v, k in found.items() if k == (status, reason)][:3]:
            log.info("    例：%s", titles[vid][:50])
    log.info("%s共 %d 筆", "（預覽，未變更）" if args.dry_run else "已標記為排除，", len(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
