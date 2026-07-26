"""文章抓取模組測試（不連真實網站）。"""
import article


class FakeMeta:
    def __init__(self, **kw):
        self.title = kw.get("title")
        self.author = kw.get("author")
        self.sitename = kw.get("sitename")
        self.date = kw.get("date")
        self.image = kw.get("image")


def _stub(monkeypatch, html="<html/>", text="正" * 500, meta=None):
    monkeypatch.setattr(article.trafilatura, "fetch_url", lambda u: html)
    monkeypatch.setattr(article.trafilatura, "extract", lambda h, **k: text)
    monkeypatch.setattr(article.trafilatura, "extract_metadata",
                        lambda h: meta if meta is not None else FakeMeta())


def test_make_id_stable_and_prefixed():
    a = article.make_id("https://example.com/post")
    assert a.startswith("art_")
    assert a == article.make_id("https://example.com/post")
    assert a != article.make_id("https://example.com/other")


def test_fetch_maps_all_fields(monkeypatch):
    _stub(monkeypatch, meta=FakeMeta(title="標題", sitename="某站",
                                     date="2026-07-01",
                                     image="https://img/a.jpg"))
    r = article.fetch("https://example.com/post")
    assert r["video_id"] == article.make_id("https://example.com/post")
    assert r["title"] == "標題"
    assert r["channel"] == "某站"
    assert r["published_at"] == "2026-07-01T00:00:00Z"
    assert r["thumbnail_url"] == "https://img/a.jpg"
    assert r["url"] == "https://example.com/post"
    assert r["content_type"] == "article"
    assert r["duration_seconds"] == 0
    assert r["view_count"] == 0


def test_fetch_truncates_body(monkeypatch):
    _stub(monkeypatch, text="字" * 5000)
    r = article.fetch("https://example.com/post", max_chars=100)
    assert len(r["description"]) == 100


def test_fetch_falls_back_to_author_then_url_host(monkeypatch):
    _stub(monkeypatch, meta=FakeMeta(title="標題", author="作者甲"))
    assert article.fetch("https://example.com/post")["channel"] == "作者甲"
    _stub(monkeypatch, meta=FakeMeta(title="標題"))
    assert article.fetch("https://example.com/post")["channel"] == "example.com"


def test_fetch_falls_back_to_url_when_no_title(monkeypatch):
    _stub(monkeypatch, meta=FakeMeta())
    assert article.fetch("https://example.com/post")["title"] == "https://example.com/post"


def test_fetch_returns_none_on_download_failure(monkeypatch):
    monkeypatch.setattr(article.trafilatura, "fetch_url", lambda u: None)

    def boom(*a, **k):
        raise article.requests.ConnectionError("連線失敗")
    monkeypatch.setattr(article._SESSION, "get", boom)
    assert article.fetch("https://example.com/post") is None


def test_fetch_returns_none_on_too_short_body(monkeypatch):
    _stub(monkeypatch, text="太短")
    assert article.fetch("https://example.com/post") is None


def test_fetch_returns_none_on_exception(monkeypatch):
    def boom(u):
        raise RuntimeError("網路炸了")
    monkeypatch.setattr(article.trafilatura, "fetch_url", boom)
    assert article.fetch("https://example.com/post") is None


def test_fetch_handles_missing_date(monkeypatch):
    _stub(monkeypatch, meta=FakeMeta(title="標題"))
    assert article.fetch("https://example.com/post")["published_at"] == ""


def test_download_uses_trafilatura_first(monkeypatch):
    monkeypatch.setattr(article.trafilatura, "fetch_url", lambda u: "<html>主要</html>")

    def boom(*a, **k):
        raise AssertionError("不應走到備援")
    monkeypatch.setattr(article._SESSION, "get", boom)
    assert article.download("https://x.com/a") == "<html>主要</html>"


def test_download_falls_back_to_session(monkeypatch):
    monkeypatch.setattr(article.trafilatura, "fetch_url", lambda u: None)

    class R:
        text = "<html>備援</html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(article._SESSION, "get", lambda *a, **k: R())
    assert article.download("https://x.com/a") == "<html>備援</html>"


def test_download_returns_none_when_both_fail(monkeypatch):
    monkeypatch.setattr(article.trafilatura, "fetch_url", lambda u: None)

    def boom(*a, **k):
        raise article.requests.ConnectionError("轉址過多")
    monkeypatch.setattr(article._SESSION, "get", boom)
    assert article.download("https://x.com/a") is None


def test_fetch_uses_download_helper(monkeypatch):
    """fetch 必須透過 download 取得 HTML（含備援），而非直接呼叫 trafilatura。"""
    monkeypatch.setattr(article, "download", lambda u: "<html/>")
    monkeypatch.setattr(article.trafilatura, "extract", lambda h, **k: "正" * 500)
    monkeypatch.setattr(article.trafilatura, "extract_metadata",
                        lambda h: type("M", (), {"title": "標題", "author": None,
                                                 "sitename": "站", "date": None,
                                                 "image": None})())
    r = article.fetch("https://x.com/a")
    assert r["title"] == "標題"


def test_fetch_rejects_javascript_scheme(monkeypatch):
    called = []
    monkeypatch.setattr(article, "download", lambda u: called.append(u))
    assert article.fetch("javascript:alert(1)") is None
    assert called == []          # 連下載都不該嘗試


def test_fetch_rejects_data_scheme(monkeypatch):
    called = []
    monkeypatch.setattr(article, "download", lambda u: called.append(u))
    assert article.fetch("data:text/html,<script>alert(1)</script>") is None
    assert called == []


def test_fetch_rejects_non_string_url(monkeypatch):
    called = []
    monkeypatch.setattr(article, "download", lambda u: called.append(u))
    assert article.fetch(None) is None
    assert article.fetch(123) is None
    assert called == []


def test_fetch_accepts_https(monkeypatch):
    monkeypatch.setattr(article, "download", lambda u: "<html/>")
    monkeypatch.setattr(article.trafilatura, "extract", lambda h, **k: "正" * 500)
    monkeypatch.setattr(article.trafilatura, "extract_metadata",
                        lambda h: type("M", (), {"title": "標題", "author": None,
                                                 "sitename": "站", "date": None,
                                                 "image": None})())
    assert article.fetch("https://example.com/post")["title"] == "標題"
