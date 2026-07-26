"""backfill 一次性回補腳本測試（不打真實 API）。"""
import backfill
import collector


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_backfill_keywords_paginates_until_no_token(monkeypatch):
    pages = iter([
        FakeResp({"items": [{"id": {"videoId": "p1"}}], "nextPageToken": "T2"}),
        FakeResp({"items": [{"id": {"videoId": "p2"}}]}),  # 無下一頁
    ])
    calls = []

    def fake_get(url, params=None, **k):
        calls.append(params or {})
        return next(pages)

    monkeypatch.setattr(backfill.requests, "get", fake_get)
    ids, used = backfill.backfill_keywords("key", ["kw"], "2025-07-26T00:00:00Z",
                                           "zh-Hant", max_pages=5)
    assert ids == ["p1", "p2"]
    assert used == 200                       # 兩頁 × 100 單位
    assert "pageToken" not in calls[0]       # 第一頁不帶 token
    assert calls[1]["pageToken"] == "T2"     # 第二頁帶上一頁的 token


def test_backfill_keywords_respects_max_pages(monkeypatch):
    monkeypatch.setattr(
        backfill.requests, "get",
        lambda *a, **k: FakeResp({"items": [{"id": {"videoId": "x"}}],
                                  "nextPageToken": "MORE"}),
    )
    ids, used = backfill.backfill_keywords("key", ["kw"], "2025-07-26T00:00:00Z",
                                           "zh-Hant", max_pages=3)
    assert used == 300  # 恰好 3 頁就停，不再翻


def test_backfill_keyword_failure_isolated(monkeypatch):
    def fake_get(url, params=None, **k):
        if params.get("q") == "壞關鍵字":
            raise collector.requests.ConnectionError("網路錯誤")
        return FakeResp({"items": [{"id": {"videoId": "ok1"}}]})

    monkeypatch.setattr(backfill.requests, "get", fake_get)
    ids, used = backfill.backfill_keywords("key", ["壞關鍵字", "好關鍵字"],
                                           "2025-07-26T00:00:00Z", "zh-Hant")
    assert ids == ["ok1"]
    assert used == 100  # 失敗那頁不計配額（未成功回應）


def test_backfill_channel_stops_at_cutoff(monkeypatch):
    responses = iter([
        # channels.list
        FakeResp({"items": [{"contentDetails":
                             {"relatedPlaylists": {"uploads": "UUabc"}}}]}),
        # playlistItems 第一頁：一部在範圍內、一部早於截止日
        FakeResp({"items": [
            {"contentDetails": {"videoId": "new1",
                                "videoPublishedAt": "2026-01-01T00:00:00Z"}},
            {"contentDetails": {"videoId": "old1",
                                "videoPublishedAt": "2024-01-01T00:00:00Z"}},
        ], "nextPageToken": "MORE"}),
    ])
    calls = []

    def fake_get(url, params=None, **k):
        calls.append(url)
        return next(responses)

    monkeypatch.setattr(backfill.requests, "get", fake_get)
    ids, used = backfill.backfill_channel("key", "@test", "2025-07-26T00:00:00Z")
    assert ids == ["new1"]      # 早於截止日的不收
    assert len(calls) == 2      # 碰到截止日就停，不翻下一頁
    assert used == 2


def test_backfill_channel_missing_uploads(monkeypatch):
    monkeypatch.setattr(
        backfill.requests, "get",
        lambda *a, **k: FakeResp({"items": [{"contentDetails": {}}]}),
    )
    ids, used = backfill.backfill_channel("key", "@broken", "2025-07-26T00:00:00Z")
    assert ids == []
    assert used == 1


def test_resolve_scope_no_override_returns_all_keywords_and_channels():
    cfg = {"keywords": ["ChatGPT", "AI 自動化"], "channels": ["@chanA", "@chanB"]}
    keywords, channels = backfill.resolve_scope(cfg, None)
    assert keywords == ["ChatGPT", "AI 自動化"]
    assert channels == ["@chanA", "@chanB"]


def test_resolve_scope_no_override_missing_channels_key_defaults_empty():
    cfg = {"keywords": ["ChatGPT"]}
    keywords, channels = backfill.resolve_scope(cfg, None)
    assert keywords == ["ChatGPT"]
    assert channels == []


def test_resolve_scope_with_override_skips_channels():
    cfg = {"keywords": ["ChatGPT", "AI 自動化", "其他"], "channels": ["@chanA"]}
    keywords, channels = backfill.resolve_scope(cfg, ["ChatGPT", "AI 自動化"])
    assert keywords == ["ChatGPT", "AI 自動化"]
    assert channels == []


def test_parse_args_default_keywords_is_none():
    args = backfill.parse_args([])
    assert args.keywords is None


def test_parse_args_with_keywords():
    args = backfill.parse_args(["--keywords", "ChatGPT", "AI 自動化"])
    assert args.keywords == ["ChatGPT", "AI 自動化"]
