"""文章抓取模組：下載網頁、抽取正文與中繼資料。

任何失敗（連不上、非文章頁、抽不出正文）一律回傳 None——
使用者貼錯連結不該讓整條管線中斷。
"""
import hashlib
import logging
import re
from urllib.parse import urlparse

import requests
import trafilatura

import collector

MIN_BODY_CHARS = 200   # 少於這個長度視為沒抽到正文

log = logging.getLogger(__name__)

_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)

# 部分網站（如經理人 managertoday.com.tw）會用反爬轉址：302 到驗證頁設 cookie 後
# 再導回原網址。trafilatura.fetch_url 不會在轉址過程中保留 cookie，因而卡在無限
# 迴圈直到「too many redirects」。改用同一個 requests.Session 當備援，
# 讓 cookie 能在轉址鏈中留存。
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
})


def make_id(url):
    """由網址產生穩定 ID，供資料庫去重使用。"""
    return "art_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def download(url):
    """下載網頁原始 HTML；失敗回傳 None。

    先用 trafilatura.fetch_url 嘗試（多數網站皆可）；若回傳假值（None 或空字串），
    改用具備 cookie 持久性的 Session 備援下載一次，因應反爬轉址迴圈。
    """
    html = trafilatura.fetch_url(url)
    if html:
        return html
    try:
        resp = _SESSION.get(url, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        log.warning("文章備援下載失敗：%s：%s", url, collector._safe_err(e))
        return None


def fetch(url, max_chars=3000):
    """抓取文章並回傳可寫入資料庫的 dict；失敗回傳 None。"""
    if not isinstance(url, str) or not _HTTP_RE.match(url):
        log.warning("非 http(s) 網址，略過：%s", str(url)[:80])
        return None
    try:
        html = download(url)
        if not html:
            log.warning("文章下載失敗：%s", url)
            return None
        text = trafilatura.extract(html, include_comments=False,
                                   include_tables=False) or ""
        if len(text) < MIN_BODY_CHARS:
            log.warning("文章抽不出正文（長度 %d）：%s", len(text), url)
            return None
        md = trafilatura.extract_metadata(html)
        title = (getattr(md, "title", None) or "").strip() or url
        channel = ((getattr(md, "sitename", None) or "").strip()
                   or (getattr(md, "author", None) or "").strip()
                   or urlparse(url).netloc)
        date = (getattr(md, "date", None) or "").strip()
        return {
            "video_id": make_id(url),
            "title": title,
            "channel": channel,
            "description": text[:max_chars],
            "published_at": f"{date}T00:00:00Z" if date else "",
            "thumbnail_url": (getattr(md, "image", None) or "").strip(),
            "duration_seconds": 0,
            "view_count": 0,
            "url": url,
            "content_type": "article",
        }
    except Exception as e:
        log.warning("文章處理失敗 %s：%s", url, e)
        return None
