"""手動提交入口：從 submit.txt 讀取使用者貼上的 YouTube 連結、文章網址或 GitHub 專案網址。

不修改該檔案——重複的影片/文章/專案由資料庫的 video_id 去重擋掉，
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

# GitHub 專案網址：取出 owner/repo，允許結尾斜線、.git、子路徑、query 與 fragment
_REPO_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)"
    r"(?:\.git)?(?:[/?#].*)?$",
    re.IGNORECASE,
)
# GitHub 自身的功能路徑，不是使用者專案
_GH_RESERVED = {
    "orgs", "settings", "marketplace", "topics", "features", "explore",
    "sponsors", "collections", "events", "notifications", "pulls", "issues",
    "codespaces", "apps", "about", "pricing", "login", "join", "search",
}


def parse_repo(url):
    """從 GitHub 專案網址取出 owner/repo；非專案網址回傳 None。"""
    m = _REPO_RE.match((url or "").strip())
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    if owner.lower() in _GH_RESERVED:
        return None
    return f"{owner}/{repo}"


def read_entries(path):
    """解析提交檔，回傳 (影片ID, 文章網址, 專案 owner/repo)，三者皆去重保序。

    判斷順序：GitHub 專案 → YouTube 影片 → 其餘 http(s) 視為文章。
    GitHub 專案網址的路徑可能剛好含有 /embed/、/shorts/ 或 ?v= 這類看似
    YouTube 的片段（例如子目錄名稱剛好叫 embed），須先判斷是否為 GitHub
    專案網址，避免被 YouTube 樣式（不限定網域的 .search()）誤先攔截。
    """
    p = Path(path)
    if not p.exists():
        return [], [], []
    videos, articles, repos = [], [], []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = parse_repo(line)
        if name:
            repos.append(name)
            continue
        vid = None
        for pat in _PATTERNS:
            m = pat.search(line)
            if m:
                vid = m.group(1)
                break
        if vid:
            videos.append(vid)
            continue
        if _HTTP_RE.match(line):
            articles.append(line)
        else:
            log.warning("無法解析的提交行，已略過：%s", line[:80])
    return (list(dict.fromkeys(videos)), list(dict.fromkeys(articles)),
            list(dict.fromkeys(repos)))


def read_ids(path):
    """相容包裝：只回傳影片 ID。"""
    return read_entries(path)[0]
