"""手動提交入口：從 submit.txt 讀取使用者貼上的 YouTube 連結。

不修改該檔案——重複的影片由資料庫的 video_id 去重擋掉，
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


def read_ids(path):
    """解析提交檔，回傳去重保序的 video_id 清單；檔案不存在回傳空清單。"""
    p = Path(path)
    if not p.exists():
        return []
    ids = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for pat in _PATTERNS:
            m = pat.search(line)
            if m:
                ids.append(m.group(1))
                break
        else:
            log.warning("無法解析的提交行，已略過：%s", line[:80])
    return list(dict.fromkeys(ids))
