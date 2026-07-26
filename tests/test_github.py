"""GitHub 專案收錄模組測試（不連真實 API）。"""
import github


class FakeResp:
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


REPO = {
    "full_name": "langgenius/dify",
    "html_url": "https://github.com/langgenius/dify",
    "description": "Build agentic workflows",
    "stargazers_count": 150278,
    "pushed_at": "2026-07-20T10:00:00Z",
    "owner": {"login": "langgenius"},
    "archived": False,
}


def test_search_returns_items(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, params=None, **k):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["params"] = params or {}
        return FakeResp({"items": [REPO]})

    monkeypatch.setattr(github.requests, "get", fake_get)
    out = github.search("tok", "AI agent", 2000, "2026-01-01")
    assert out == [REPO]
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert "tok" not in captured["url"]                    # token 不得出現在網址
    assert "stars:>2000" in captured["params"]["q"]
    assert "pushed:>2026-01-01" in captured["params"]["q"]


def test_search_failure_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise github.requests.ConnectionError("網路錯誤")
    monkeypatch.setattr(github.requests, "get", boom)
    assert github.search("tok", "AI", 100, "2026-01-01") == []


def test_search_skips_archived(monkeypatch):
    archived = dict(REPO, full_name="old/dead", archived=True)
    monkeypatch.setattr(github.requests, "get",
                        lambda *a, **k: FakeResp({"items": [REPO, archived]}))
    out = github.search("tok", "AI", 100, "2026-01-01")
    assert [r["full_name"] for r in out] == ["langgenius/dify"]


def test_fetch_readme_truncates(monkeypatch):
    monkeypatch.setattr(github.requests, "get",
                        lambda *a, **k: FakeResp(text="A" * 5000))
    assert len(github.fetch_readme("tok", "a/b", max_chars=100)) == 100


def test_fetch_readme_failure_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise github.requests.ConnectionError("沒有 README")
    monkeypatch.setattr(github.requests, "get", boom)
    assert github.fetch_readme("tok", "a/b") == ""


def test_to_item_maps_fields():
    item = github.to_item(REPO, "README 內容")
    assert item["video_id"] == "gh_langgenius_dify"
    assert item["title"] == "langgenius/dify"
    assert item["channel"] == "langgenius"
    assert item["description"] == "README 內容"
    assert item["published_at"] == "2026-07-20T10:00:00Z"
    assert item["thumbnail_url"] == "https://opengraph.githubassets.com/1/langgenius/dify"
    assert item["view_count"] == 150278
    assert item["duration_seconds"] == 0
    assert item["url"] == "https://github.com/langgenius/dify"
    assert item["content_type"] == "repo"


def test_to_item_falls_back_to_description_when_no_readme():
    item = github.to_item(REPO, "")
    assert item["description"] == "Build agentic workflows"


def test_discover_dedups_across_queries(monkeypatch):
    monkeypatch.setattr(github, "search", lambda *a, **k: [REPO])
    monkeypatch.setattr(github, "fetch_readme", lambda *a, **k: "README")
    items = github.discover("tok", ["AI agent", "LLM"], 2000, 180)
    assert len(items) == 1                                  # 兩個查詢撈到同一個專案只留一筆


def test_discover_empty_queries(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("不應呼叫")
    monkeypatch.setattr(github, "search", boom)
    assert github.discover("tok", [], 2000, 180) == []
