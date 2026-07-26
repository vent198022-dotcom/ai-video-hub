"""文章抓取模組：下載網頁、抽取正文與中繼資料。

任何失敗（連不上、非文章頁、抽不出正文）一律回傳 None——
使用者貼錯連結不該讓整條管線中斷。
"""
import hashlib
import logging
from urllib.parse import urlparse

import trafilatura

MIN_BODY_CHARS = 200   # 少於這個長度視為沒抽到正文

log = logging.getLogger(__name__)


def make_id(url):
    """由網址產生穩定 ID，供資料庫去重使用。"""
    return "art_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def fetch(url, max_chars=3000):
    """抓取文章並回傳可寫入資料庫的 dict；失敗回傳 None。"""
    try:
        html = trafilatura.fetch_url(url)
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
