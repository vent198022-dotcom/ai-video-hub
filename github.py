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
SCORECARD_URL = "https://api.securityscorecards.dev/projects/github.com/{full_name}"
TIMEOUT = 30

_NO_LICENSE = {"", "NOASSERTION", "NONE"}

log = logging.getLogger(__name__)


def has_open_license(repo):
    """是否有明確的開源授權條款。無授權的專案公司採用有法律風險，一律不收。"""
    spdx = ((repo.get("license") or {}).get("spdx_id") or "").strip()
    return bool(spdx) and spdx.upper() not in _NO_LICENSE


def fetch_scorecard(full_name):
    """查 OpenSSF 安全評分（0~10）；查無或失敗回 None。

    涵蓋率不完整是正常現象——查無資料代表「未知」，不代表不安全，
    因此絕不可用它來排除專案。
    """
    try:
        resp = requests.get(SCORECARD_URL.format(full_name=full_name),
                            timeout=TIMEOUT)
        resp.raise_for_status()
        score = resp.json().get("score")
        return (float(score)
                if isinstance(score, (int, float)) and not isinstance(score, bool)
                else None)
    except (requests.RequestException, ValueError, TypeError, AttributeError) as e:
        log.debug("專案 %s 查無安全評分：%s", full_name, collector._safe_err(e))
        return None


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
    kept, no_license = [], 0
    for r in items:
        if not isinstance(r, dict) or r.get("archived"):
            continue
        if not has_open_license(r):
            no_license += 1
            continue
        kept.append(r)
    if no_license:
        log.info("查詢「%s」：%d 個專案因無明確開源授權被排除", query, no_license)
    return kept


REPO_URL = "https://api.github.com/repos/{full_name}"


def fetch_repo(token, full_name):
    """查詢單一專案（供手動指定使用）；查不到、已封存或失敗回傳 None。

    不檢查授權條款——手動指定代表使用者已自行判斷，與手動提交影片
    不受時長限制同理。
    """
    try:
        resp = requests.get(REPO_URL.format(full_name=full_name),
                            headers=_headers(token), timeout=TIMEOUT)
        resp.raise_for_status()
        repo = resp.json()
    except (requests.RequestException, ValueError) as e:
        log.warning("查詢專案「%s」失敗：%s", full_name, collector._safe_err(e))
        return None
    if not isinstance(repo, dict) or not repo.get("full_name"):
        log.warning("專案「%s」回應格式異常，略過", full_name)
        return None
    if repo.get("archived"):
        log.info("專案「%s」已封存，略過", full_name)
        return None
    return repo


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


def to_item(repo, readme, score=None):
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
        "license": ((repo.get("license") or {}).get("spdx_id") or ""),
        "security_score": score,
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
    return [to_item(r, fetch_readme(token, n), fetch_scorecard(n))
            for n, r in seen.items()]
