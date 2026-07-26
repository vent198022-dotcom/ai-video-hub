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


SITEMAP_INDEX_MIXED = """<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://z.com/feed/article/1.xml</loc></sitemap>
  <sitemap><loc>https://z.com/feed/article/2.xml</loc></sitemap>
  <sitemap><loc>https://z.com/feed/media/1.xml</loc></sitemap>
</sitemapindex>"""


def test_discover_sitemap_filter_picks_last_matching(monkeypatch):
    """索引尾端接了非文章子檔時，要取最後一個「文章」子檔而非最後一個。"""
    seen = []

    def fake_fetch(url):
        seen.append(url)
        return SITEMAP_INDEX_MIXED if url.endswith("sitemap.xml") else SITEMAP_URLS

    monkeypatch.setattr(sites, "fetch_xml", fake_fetch)
    sites.discover({"name": "某站", "sitemap": "https://z.com/feed/sitemap.xml",
                    "sitemap_filter": "/article/"}, KW)
    assert seen[1] == "https://z.com/feed/article/2.xml"


def test_discover_sitemap_filter_no_match_returns_empty(monkeypatch):
    monkeypatch.setattr(sites, "fetch_xml", lambda url: SITEMAP_INDEX_MIXED)
    assert sites.discover({"name": "某站", "sitemap": "https://z.com/feed/sitemap.xml",
                           "sitemap_filter": "/nothing/"}, KW) == []


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


LISTING_HTML = """<html><body>
  <a href="/article/131794">第一篇</a>
  <a href="/article/131681">第二篇</a>
  <a href="/article/131794">重複的第一篇</a>
  <a href="/about">關於我們</a>
  <a href="https://www.gvm.com.tw/article/131458">絕對網址那篇</a>
</body></html>"""

BNEXT_HTML = """<html><body>
  <a href="/article/91612/salesforce-ai-sales-use-cases">A</a>
  <a href="/article/91588/anthropic-claude-financial-agents-guide">B</a>
  <a href="/categories/ai">分類連結不要</a>
</body></html>"""


def test_extract_links_relative_to_absolute():
    urls = sites.extract_links(LISTING_HTML, "https://www.gvm.com.tw/category/how-to",
                               r"/article/\d+")
    assert urls == [
        "https://www.gvm.com.tw/article/131794",
        "https://www.gvm.com.tw/article/131681",
        "https://www.gvm.com.tw/article/131458",
    ]


def test_extract_links_with_slug_pattern():
    urls = sites.extract_links(BNEXT_HTML, "https://www.bnext.com.tw/categories/ai",
                               r"/article/\d+/[a-z0-9-]+")
    assert urls == [
        "https://www.bnext.com.tw/article/91612/salesforce-ai-sales-use-cases",
        "https://www.bnext.com.tw/article/91588/anthropic-claude-financial-agents-guide",
    ]


def test_extract_links_empty_inputs():
    assert sites.extract_links("", "https://x.com", r"/article/\d+") == []
    assert sites.extract_links(LISTING_HTML, "https://x.com", "") == []


def test_extract_links_invalid_regex_returns_empty():
    assert sites.extract_links(LISTING_HTML, "https://x.com", "[unclosed") == []


def test_discover_page_source(monkeypatch):
    monkeypatch.setattr(sites, "fetch_xml", lambda url: LISTING_HTML)
    urls = sites.discover({"name": "遠見", "page": "https://www.gvm.com.tw/category/how-to",
                           "link_pattern": r"/article/\d+", "filter": False}, KW)
    assert len(urls) == 3
    assert urls[0] == "https://www.gvm.com.tw/article/131794"


def test_discover_page_respects_max(monkeypatch):
    monkeypatch.setattr(sites, "fetch_xml", lambda url: LISTING_HTML)
    urls = sites.discover({"name": "遠見", "page": "https://x.com/c",
                           "link_pattern": r"/article/\d+", "filter": False},
                          KW, max_items=2)
    assert len(urls) == 2


def test_discover_page_missing_pattern_returns_empty(monkeypatch):
    monkeypatch.setattr(sites, "fetch_xml", lambda url: LISTING_HTML)
    assert sites.discover({"name": "怪站", "page": "https://x.com/c"}, KW) == []


def test_discover_page_fetch_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(sites, "fetch_xml", lambda url: None)
    assert sites.discover({"name": "遠見", "page": "https://x.com/c",
                           "link_pattern": r"/article/\d+"}, KW) == []


def test_filter_false_skips_keyword_screening(monkeypatch):
    """關閉篩選時，連標題完全不含關鍵字的項目也要收下。"""
    monkeypatch.setattr(sites, "fetch_xml", lambda url: RSS_XML)
    urls = sites.discover({"name": "某站", "feed": "https://x.com/rss", "filter": False}, KW)
    assert urls == ["https://x.com/a1", "https://x.com/a2", "https://x.com/a3"]


def test_filter_defaults_to_true(monkeypatch):
    """未指定 filter 時維持原本會篩選的行為。"""
    monkeypatch.setattr(sites, "fetch_xml", lambda url: RSS_XML)
    urls = sites.discover({"name": "某站", "feed": "https://x.com/rss"}, KW)
    assert urls == ["https://x.com/a1", "https://x.com/a3"]
