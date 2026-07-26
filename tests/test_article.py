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
