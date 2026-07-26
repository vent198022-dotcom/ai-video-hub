"""網站文章發現模組測試（不連真實網站）。"""
import sites

RSS_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>某站</title>
  <item><title>AI 教學：從零開始</title><link>https://x.com/a1</link></item>
  <item><title>股市分析週報</title><link>https://x.com/a2</link></item>
  <item><title>用 ChatGPT 寫報告</title><link>https://x.com/a3</link></item>
</channel></rss>"""

ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Claude 實戰</title><link href="https://y.com/b1"/></entry>
  <entry><title>午餐吃什麼</title><link href="https://y.com/b2"/></entry>
</feed>"""

SITEMAP_INDEX = """<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://z.com/feed/article/1.xml</loc></sitemap>
  <sitemap><loc>https://z.com/feed/article/2.xml</loc></sitemap>
</sitemapindex>"""

SITEMAP_URLS = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://z.com/article/1/retail-seller-report</loc></url>
  <url><loc>https://z.com/article/2/ai-agent-guide</loc></url>
  <url><loc>https://z.com/article/3/chatgpt-for-work</loc></url>
</urlset>"""

KW = ["AI", "ChatGPT", "Claude", "agent", "自動化"]


def test_parse_rss():
    assert sites.parse_rss(RSS_XML) == [
        ("AI 教學：從零開始", "https://x.com/a1"),
        ("股市分析週報", "https://x.com/a2"),
        ("用 ChatGPT 寫報告", "https://x.com/a3"),
    ]


def test_parse_atom():
    assert sites.parse_rss(ATOM_XML) == [
        ("Claude 實戰", "https://y.com/b1"),
        ("午餐吃什麼", "https://y.com/b2"),
    ]


def test_parse_rss_malformed_returns_empty():
    assert sites.parse_rss("<not xml") == []
    assert sites.parse_rss("") == []


def test_parse_sitemap_locs():
    assert sites.parse_sitemap_locs(SITEMAP_INDEX) == [
        "https://z.com/feed/article/1.xml",
        "https://z.com/feed/article/2.xml",
    ]


def test_parse_sitemap_malformed_returns_empty():
    assert sites.parse_sitemap_locs("<broken") == []


def test_title_matches_case_insensitive():
    assert sites.title_matches("用 chatgpt 寫報告", KW) is True
    assert sites.title_matches("股市分析週報", KW) is False


def test_slug_matches_requires_whole_token():
    # ai 不可誤中 retail
    assert sites.slug_matches("https://z.com/article/1/retail-seller-report", KW) is False
    assert sites.slug_matches("https://z.com/article/2/ai-agent-guide", KW) is True
    assert sites.slug_matches("https://z.com/article/3/chatgpt-for-work", KW) is True


def test_slug_matches_ignores_non_latin_keywords():
    # 中文關鍵字對英文 slug 無效，不得因此誤判
    assert sites.slug_matches("https://z.com/a/some-post", ["自動化"]) is False


def test_discover_feed_filters_by_title(monkeypatch):
    monkeypatch.setattr(sites, "fetch_xml", lambda url: RSS_XML)
    urls = sites.discover({"name": "某站", "feed": "https://x.com/rss"}, KW)
    assert urls == ["https://x.com/a1", "https://x.com/a3"]   # 股市那篇被篩掉


def test_discover_feed_respects_max(monkeypatch):
    monkeypatch.setattr(sites, "fetch_xml", lambda url: RSS_XML)
    urls = sites.discover({"name": "某站", "feed": "https://x.com/rss"}, KW, max_items=1)
    assert urls == ["https://x.com/a1"]


def test_discover_sitemap_uses_last_subsitemap(monkeypatch):
    """sitemap index 的最後一個子檔才是最新文章。"""
    seen = []

    def fake_fetch(url):
        seen.append(url)
        return SITEMAP_INDEX if url.endswith("sitemap.xml") else SITEMAP_URLS

    monkeypatch.setattr(sites, "fetch_xml", fake_fetch)
    urls = sites.discover({"name": "某站", "sitemap": "https://z.com/feed/sitemap.xml"}, KW)
    assert seen[1] == "https://z.com/feed/article/2.xml"      # 取最後一個子檔
    assert urls == [
        "https://z.com/article/3/chatgpt-for-work",           # 新到舊
        "https://z.com/article/2/ai-agent-guide",
    ]


def test_discover_network_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(sites, "fetch_xml", lambda url: None)
    assert sites.discover({"name": "某站", "feed": "https://x.com/rss"}, KW) == []
    assert sites.discover({"name": "某站", "sitemap": "https://z.com/s.xml"}, KW) == []


def test_discover_unknown_source_returns_empty():
    assert sites.discover({"name": "怪站"}, KW) == []


def test_fetch_xml_returns_none_on_error(monkeypatch):
    def boom(*a, **k):
        raise sites.requests.ConnectionError("網路錯誤")
    monkeypatch.setattr(sites.requests, "get", boom)
    assert sites.fetch_xml("https://x.com/rss") is None
