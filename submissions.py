"""手動提交入口：從 submit.txt 讀取使用者貼上的 YouTube 連結或文章網址。

不修改該檔案——重複的影片/文章由資料庫的 video_id 去重擋掉，
檔案本身就是一份提交紀錄。
"""
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# 依序比對：watch?v=、youtu.be/、shorts/、embed/、或整行就是 11 碼影片 ID
_PATTERNS = [
    re.compile(r"[?&]v=([A-Za-z0-9_-]{11})"),
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})"),
    re.compile(r"/shorts/([A-Za-z0-9_-]{11})"),
    re.compile(r"/embed/([A-Za-z0-9_-]{11})"),
    re.compile(r"^([A-Za-z0-9_-]{11})$"),
]

_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)


def read_entries(path):
    """解析提交檔，回傳 (影片ID清單, 文章網址清單)，兩者皆去重保序。

    能解析出 YouTube 影片 ID 的視為影片；其餘 http(s) 開頭的視為文章網址。
    """
    p = Path(path)
    if not p.exists():
        return [], []
    videos, articles = [], []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for pat in _PATTERNS:
            m = pat.search(line)
            if m:
                videos.append(m.group(1))
                break
        else:
            if _HTTP_RE.match(line):
                articles.append(line)
            else:
                log.warning("無法解析的提交行，已略過：%s", line[:80])
    return list(dict.fromkeys(videos)), list(dict.fromkeys(articles))


def read_ids(path):
    """相容包裝：只回傳影片 ID。"""
    return read_entries(path)[0]
