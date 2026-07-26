"""GitHub 開源專案收錄模組：搜尋專案、抓 README，轉成可入庫的內容。

任何 API 失敗一律回傳空值並記錄警告——單一查詢失敗不得中斷整條管線。
"""
import logging
from datetime import datetime, timedelta, timezone

import requests

import collector

SEARCH_URL = "https://api.github.com/search/repositories"
README_URL = "https://api.github.com/repos/{full_name}/readme"
OG_IMAGE_URL = "https://opengraph.githubassets.com/1/{full_name}"
TIMEOUT = 30

log = logging.getLogger(__name__)


def _headers(token, raw=False):
    """GitHub API 標頭。token 一律放標頭，不得放網址。"""
    h = {"Accept": "application/vnd.github.raw" if raw
         else "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def search(token, query, min_stars, pushed_after, per_page=20):
    """搜尋專案，回傳原始 repo dict 清單（已排除封存專案）；失敗回傳空清單。"""
    q = f"{query} in:name,description,topics stars:>{min_stars} pushed:>{pushed_after}"
    params = {"q": q, "sort": "stars", "order": "desc", "per_page": per_page}
    try:
        resp = requests.get(SEARCH_URL, headers=_headers(token),
                            params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except (requests.RequestException, ValueError, AttributeError) as e:
        log.warning("GitHub 搜尋「%s」失敗：%s", query, collector._safe_err(e))
        return []
    return [r for r in items if isinstance(r, dict) and not r.get("archived")]


def fetch_readme(token, full_name, max_chars=3000):
    """抓取專案 README 純文字（截斷）；抓不到回傳空字串。"""
    try:
        resp = requests.get(README_URL.format(full_name=full_name),
                            headers=_headers(token, raw=True), timeout=TIMEOUT)
        resp.raise_for_status()
        return (resp.text or "")[:max_chars]
    except requests.RequestException as e:
        log.debug("專案 %s 無法取得 README：%s", full_name, collector._safe_err(e))
        return ""


def to_item(repo, readme):
    """把 GitHub repo 轉成可寫入資料庫的內容 dict。"""
    full_name = repo["full_name"]
    return {
        "video_id": "gh_" + full_name.replace("/", "_"),
        "title": full_name,
        "channel": (repo.get("owner") or {}).get("login", ""),
        "description": readme or (repo.get("description") or ""),
        "published_at": repo.get("pushed_at", ""),
        "thumbnail_url": OG_IMAGE_URL.format(full_name=full_name),
        "duration_seconds": 0,
        "view_count": int(repo.get("stargazers_count") or 0),
        "url": repo.get("html_url", ""),
        "content_type": "repo",
    }


def discover(token, queries, min_stars, pushed_days, per_query=20):
    """跑完所有查詢並抓 README，回傳去重後的內容清單。"""
    if not queries:
        return []
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=pushed_days)).strftime("%Y-%m-%d")
    seen = {}
    for q in queries:
        for repo in search(token, q, min_stars, cutoff, per_query):
            name = repo.get("full_name")
            if name and name not in seen:
                seen[name] = repo
        log.info("GitHub 查詢「%s」：累計 %d 個專案", q, len(seen))
    return [to_item(r, fetch_readme(token, n)) for n, r in seen.items()]
