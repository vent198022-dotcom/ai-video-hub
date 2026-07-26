"""網站文章發現模組：從各站的 RSS 或 sitemap 找出可能相關的文章網址。

只負責「找網址」，抓正文與分類交由 article.py 與既有管線處理。
任何網站失敗一律回傳空清單並記錄警告——單站故障不得影響其他站或整條管線。
"""
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import requests

import collector

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TIMEOUT = 30

log = logging.getLogger(__name__)

_LATIN_RE = re.compile(r"^[A-Za-z0-9]+$")
_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")


def fetch_xml(url):
    """下載 XML 文字；失敗回傳 None。"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        log.warning("下載失敗 %s：%s", url, collector._safe_err(e))
        return None


def _localname(tag):
    """去掉 XML 命名空間，例如 '{...}entry' -> 'entry'。"""
    return tag.rsplit("}", 1)[-1]


def parse_rss(xml_text):
    """解析 RSS 或 Atom，回傳 [(標題, 網址)]；解析失敗回傳空清單。"""
    try:
        root = ET.fromstring(xml_text or "")
    except ET.ParseError:
        return []
    out = []
    for node in root.iter():
        name = _localname(node.tag)
        if name not in ("item", "entry"):
            continue
        title = link = None
        for child in node:
            cname = _localname(child.tag)
            if cname == "title" and title is None:
                title = (child.text or "").strip()
            elif cname == "link" and link is None:
                # RSS 放在文字節點，Atom 放在 href 屬性
                link = (child.get("href") or child.text or "").strip()
        if title and link:
            out.append((title, link))
    return out


def parse_sitemap_locs(xml_text):
    """取出 sitemap（index 或一般）中所有 <loc>；解析失敗回傳空清單。"""
    try:
        root = ET.fromstring(xml_text or "")
    except ET.ParseError:
        return []
    return [(n.text or "").strip() for n in root.iter()
            if _localname(n.tag) == "loc" and (n.text or "").strip()]


def title_matches(title, keywords):
    """標題含任一關鍵字（不分大小寫）。"""
    low = (title or "").lower()
    return any(k.lower() in low for k in keywords)


def slug_matches(url, keywords):
    """網址 token 完整命中任一英數關鍵字。

    只比對純英數關鍵字並要求完整 token 相符，避免 'ai' 誤中 'retail'。
    中文關鍵字對英文網址無意義，一律略過。
    """
    tokens = {t for t in _TOKEN_RE.split((url or "").lower()) if t}
    latin = {k.lower() for k in keywords if _LATIN_RE.match(k)}
    return bool(tokens & latin)


_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


def extract_links(html, base_url, pattern):
    """從 HTML 列表頁抽出符合 pattern 的文章連結，轉為絕對網址並去重保序。

    pattern 無效或輸入為空時回傳空清單——單一來源設定寫錯不得中斷管線。
    """
    if not html or not pattern:
        return []
    try:
        pat = re.compile(pattern)
    except re.error as e:
        log.warning("link_pattern 無效（%s）：%s", pattern, e)
        return []
    out = []
    for href in _HREF_RE.findall(html):
        if pat.search(href):
            out.append(urljoin(base_url, href))
    return list(dict.fromkeys(out))


def discover(site, keywords, max_items=20):
    """回傳該來源篩選後的文章網址（最多 max_items 筆）。

    來源型態擇一：feed（RSS／Atom）、sitemap（sitemap index）、page（HTML 列表頁）。
    site["filter"] 設為 False 時略過關鍵字預篩——分類頁本身已鎖定主題，
    再篩會誤殺（例如遠見的文章網址是純數字，比對不到任何關鍵字）。
    """
    name = site.get("name", "?")
    use_filter = site.get("filter", True)

    if site.get("feed"):
        xml_text = fetch_xml(site["feed"])
        if not xml_text:
            return []
        entries = parse_rss(xml_text)
        hits = [url for title, url in entries
                if not use_filter or title_matches(title, keywords)]
    elif site.get("sitemap"):
        index_xml = fetch_xml(site["sitemap"])
        if not index_xml:
            return []
        subs = parse_sitemap_locs(index_xml)
        needle = site.get("sitemap_filter")
        if needle:
            subs = [s for s in subs if needle in s]
        if not subs:
            log.warning("網站「%s」的 sitemap 找不到符合的子檔，略過", name)
            return []
        # 子 sitemap 由舊到新排列，最後一個才是最新文章
        last_xml = fetch_xml(subs[-1])
        if not last_xml:
            return []
        # 檔內同樣由舊到新，反轉後取最新的
        locs = list(reversed(parse_sitemap_locs(last_xml)))
        hits = [u for u in locs if not use_filter or slug_matches(u, keywords)]
    elif site.get("page"):
        pattern = site.get("link_pattern")
        if not pattern:
            log.warning("網站「%s」設定了 page 但缺少 link_pattern，略過", name)
            return []
        html = fetch_xml(site["page"])
        if not html:
            return []
        links = extract_links(html, site["page"], pattern)
        hits = [u for u in links if not use_filter or slug_matches(u, keywords)]
    else:
        log.warning("網站「%s」未設定 feed／sitemap／page，略過", name)
        return []

    result = hits[:max_items]
    log.info("來源「%s」：取得 %d 篇（上限 %d%s）", name, len(result), max_items,
             "" if use_filter else "，未套關鍵字篩選")
    return result
