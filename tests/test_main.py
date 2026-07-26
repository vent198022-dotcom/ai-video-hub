"""main 管線測試：只驗證金鑰檢查與階段串接，不打真實 API。"""
import main as main_mod


def test_main_fails_without_keys(monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert main_mod.main() == 1


def test_main_runs_all_stages(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-key")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)

    (tmp_path / "config.yaml").write_text(
        "keywords: [kw1]\ncategories: [工具教學]\n"
        "filters: {min_duration_seconds: 120, relevance_language: zh-Hant,"
        " max_results_per_keyword: 25, initial_days: 180}\n"
        "gemini: {model: gemini-2.5-flash, batch_size: 10}\n"
        "transcript: {enabled: false, max_chars: 3000, batch_size: 5}\n",
        encoding="utf-8",
    )

    stages = []
    monkeypatch.setattr(main_mod.collector, "collect",
                        lambda *a, **k: stages.append("collect") or 3)
    monkeypatch.setattr(main_mod.classifier, "classify_pending",
                        lambda *a, **k: stages.append("classify") or (2, 1, 0))
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 2)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or True)

    assert main_mod.main() == 0
    assert stages == ["collect", "classify", "generate", "publish"]


def test_main_collect_failure_still_continues(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-key")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        "keywords: [kw1]\ncategories: [工具教學]\n"
        "filters: {min_duration_seconds: 120, relevance_language: zh-Hant,"
        " max_results_per_keyword: 25, initial_days: 180}\n"
        "gemini: {model: gemini-2.5-flash, batch_size: 10}\n"
        "transcript: {enabled: false, max_chars: 3000, batch_size: 5}\n",
        encoding="utf-8",
    )

    def boom(*a, **k):
        raise RuntimeError("收集掛了")
    stages = []
    monkeypatch.setattr(main_mod.collector, "collect", boom)
    monkeypatch.setattr(main_mod.classifier, "classify_pending",
                        lambda *a, **k: stages.append("classify") or (0, 0, 0))
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 0)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or False)

    assert main_mod.main() == 0
    assert stages == ["classify", "generate", "publish"]


def test_main_runs_cleanup_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        "keywords: [kw1]\ncategories: [工具教學]\n"
        "filters: {min_duration_seconds: 120, relevance_language: zh-Hant,"
        " max_results_per_keyword: 25, initial_days: 180}\n"
        "gemini: {model: m, batch_size: 10, pause_seconds: 0}\n"
        "transcript: {enabled: false, max_chars: 3000, batch_size: 5}\n",
        encoding="utf-8",
    )
    stages = []
    monkeypatch.setattr(main_mod.collector, "collect",
                        lambda *a, **k: stages.append("collect") or 0)
    monkeypatch.setattr(main_mod.classifier, "classify_pending",
                        lambda *a, **k: stages.append("classify") or (0, 0, 0))
    monkeypatch.setattr(main_mod.cleanup, "remove_dead_videos",
                        lambda *a, **k: stages.append("cleanup") or 0)
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 0)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or False)

    assert main_mod.main() == 0
    assert stages == ["collect", "classify", "cleanup", "generate", "publish"]


def test_main_cleanup_failure_does_not_stop_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        "keywords: [kw1]\ncategories: [工具教學]\n"
        "filters: {min_duration_seconds: 120, relevance_language: zh-Hant,"
        " max_results_per_keyword: 25, initial_days: 180}\n"
        "gemini: {model: m, batch_size: 10, pause_seconds: 0}\n"
        "transcript: {enabled: false, max_chars: 3000, batch_size: 5}\n",
        encoding="utf-8",
    )
    stages = []
    monkeypatch.setattr(main_mod.collector, "collect", lambda *a, **k: 0)
    monkeypatch.setattr(main_mod.classifier, "classify_pending",
                        lambda *a, **k: (0, 0, 0))

    def boom(*a, **k):
        raise RuntimeError("清理掛了")
    monkeypatch.setattr(main_mod.cleanup, "remove_dead_videos", boom)
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 0)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or False)

    assert main_mod.main() == 0
    assert stages == ["generate", "publish"]


def test_main_fetches_submitted_articles(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        "keywords: []\ncategories: [工具教學]\n"
        "filters: {min_duration_seconds: 120, relevance_language: zh-Hant,"
        " max_results_per_keyword: 25, initial_days: 180}\n"
        "gemini: {model: m, batch_size: 10, pause_seconds: 0}\n"
        "transcript: {enabled: false, max_chars: 3000, batch_size: 5}\n"
        "article: {max_chars: 3000}\n",
        encoding="utf-8",
    )
    (tmp_path / "submit.txt").write_text(
        "https://example.com/good\nhttps://example.com/bad\n", encoding="utf-8")

    monkeypatch.setattr(main_mod.collector, "collect", lambda *a, **k: 0)
    monkeypatch.setattr(main_mod.classifier, "classify_pending",
                        lambda *a, **k: (0, 0, 0))
    monkeypatch.setattr(main_mod.cleanup, "remove_dead_videos", lambda *a, **k: 0)
    monkeypatch.setattr(main_mod.generator, "generate", lambda *a, **k: 0)
    monkeypatch.setattr(main_mod.publisher, "publish", lambda *a, **k: False)

    def fake_article_fetch(url, max_chars=3000):
        if url.endswith("bad"):
            return None            # 抓不到的要略過，不得中斷
        return {
            "video_id": "art_good", "title": "好文章", "channel": "站",
            "description": "內文", "published_at": "2026-07-01T00:00:00Z",
            "thumbnail_url": "", "duration_seconds": 0, "view_count": 0,
            "url": url, "content_type": "article",
        }
    monkeypatch.setattr(main_mod.article, "fetch", fake_article_fetch)

    assert main_mod.main() == 0
    conn = main_mod.db.connect(tmp_path / "videos.db")
    assert main_mod.db.video_exists(conn, "art_good")


def test_main_article_failure_does_not_stop_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        "keywords: []\ncategories: [工具教學]\n"
        "filters: {min_duration_seconds: 120, relevance_language: zh-Hant,"
        " max_results_per_keyword: 25, initial_days: 180}\n"
        "gemini: {model: m, batch_size: 10, pause_seconds: 0}\n"
        "transcript: {enabled: false, max_chars: 3000, batch_size: 5}\n"
        "article: {max_chars: 3000}\n",
        encoding="utf-8",
    )
    (tmp_path / "submit.txt").write_text(
        "https://example.com/good\n", encoding="utf-8")

    stages = []
    monkeypatch.setattr(main_mod.collector, "collect", lambda *a, **k: 0)
    monkeypatch.setattr(main_mod.classifier, "classify_pending",
                        lambda *a, **k: stages.append("classify") or (0, 0, 0))
    monkeypatch.setattr(main_mod.cleanup, "remove_dead_videos", lambda *a, **k: 0)
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 0)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or False)

    def boom(*a, **k):
        raise RuntimeError("文章收集掛了")
    monkeypatch.setattr(main_mod.article, "fetch", boom)

    assert main_mod.main() == 0
    assert stages == ["classify", "generate", "publish"]


def _write_cfg(tmp_path, extra=""):
    (tmp_path / "config.yaml").write_text(
        "keywords: []\ncategories: [工具教學]\n"
        "filters: {min_duration_seconds: 120, relevance_language: zh-Hant,"
        " max_results_per_keyword: 25, initial_days: 180}\n"
        "gemini: {model: m, batch_size: 10, pause_seconds: 0}\n"
        "transcript: {enabled: false, max_chars: 3000, batch_size: 5}\n"
        "article: {max_chars: 3000}\n" + extra,
        encoding="utf-8",
    )


def _stub_stages(monkeypatch):
    monkeypatch.setattr(main_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(main_mod.collector, "collect", lambda *a, **k: 0)
    monkeypatch.setattr(main_mod.classifier, "classify_pending",
                        lambda *a, **k: (0, 0, 0))
    monkeypatch.setattr(main_mod.cleanup, "remove_dead_videos", lambda *a, **k: 0)
    monkeypatch.setattr(main_mod.generator, "generate", lambda *a, **k: 0)
    monkeypatch.setattr(main_mod.publisher, "publish", lambda *a, **k: False)


def test_main_collects_from_sites(tmp_path, monkeypatch):
    _stub_stages(monkeypatch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    _write_cfg(tmp_path,
               "sites: [{name: 某站, feed: 'https://x.com/rss'}]\n"
               "site_filter: {max_per_site: 20, match: [AI]}\n")

    monkeypatch.setattr(main_mod.sites, "discover",
                        lambda site, kw, max_items=20: ["https://x.com/found"])
    monkeypatch.setattr(main_mod.article, "fetch", lambda url, mc=3000: {
        "video_id": main_mod.article.make_id(url), "title": "站內文章",
        "channel": "某站", "description": "內文", "published_at": "",
        "thumbnail_url": "", "duration_seconds": 0, "view_count": 0,
        "url": url, "content_type": "article",
    })

    assert main_mod.main() == 0
    conn = main_mod.db.connect(tmp_path / "videos.db")
    assert main_mod.db.video_exists(conn, main_mod.article.make_id("https://x.com/found"))


def test_main_site_discovery_failure_does_not_stop_pipeline(tmp_path, monkeypatch):
    _stub_stages(monkeypatch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    _write_cfg(tmp_path,
               "sites: [{name: 壞站, feed: 'https://x.com/rss'}]\n"
               "site_filter: {max_per_site: 20, match: [AI]}\n")

    stages = []

    def boom(*a, **k):
        raise RuntimeError("發現階段掛了")
    monkeypatch.setattr(main_mod.sites, "discover", boom)
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 0)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or False)

    assert main_mod.main() == 0
    assert stages == ["generate", "publish"]


def test_main_no_sites_configured(tmp_path, monkeypatch):
    """沒設定 sites 時不得出錯。"""
    _stub_stages(monkeypatch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    _write_cfg(tmp_path)

    def boom(*a, **k):
        raise AssertionError("不應呼叫 discover")
    monkeypatch.setattr(main_mod.sites, "discover", boom)
    assert main_mod.main() == 0


def test_main_collects_github_repos(tmp_path, monkeypatch):
    _stub_stages(monkeypatch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setenv("GITHUB_TOKEN", "gh")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    _write_cfg(tmp_path,
               "github: {enabled: true, queries: [AI agent], min_stars: 2000,"
               " pushed_days: 180, per_query: 20, readme_chars: 3000}\n")

    monkeypatch.setattr(main_mod.github, "discover", lambda *a, **k: [{
        "video_id": "gh_foo_bar", "title": "foo/bar", "channel": "foo",
        "description": "README", "published_at": "2026-07-01T00:00:00Z",
        "thumbnail_url": "https://img", "duration_seconds": 0,
        "view_count": 100, "url": "https://github.com/foo/bar",
        "content_type": "repo",
    }])

    assert main_mod.main() == 0
    conn = main_mod.db.connect(tmp_path / "videos.db")
    assert main_mod.db.video_exists(conn, "gh_foo_bar")


def test_main_github_failure_does_not_stop_pipeline(tmp_path, monkeypatch):
    _stub_stages(monkeypatch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setenv("GITHUB_TOKEN", "gh")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    _write_cfg(tmp_path,
               "github: {enabled: true, queries: [AI], min_stars: 1,"
               " pushed_days: 30, per_query: 5, readme_chars: 3000}\n")

    stages = []

    def boom(*a, **k):
        raise RuntimeError("GitHub 掛了")
    monkeypatch.setattr(main_mod.github, "discover", boom)
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 0)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or False)

    assert main_mod.main() == 0
    assert stages == ["generate", "publish"]


def test_main_github_disabled(tmp_path, monkeypatch):
    _stub_stages(monkeypatch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    _write_cfg(tmp_path, "github: {enabled: false, queries: [AI]}\n")

    def boom(*a, **k):
        raise AssertionError("關閉時不應呼叫 discover")
    monkeypatch.setattr(main_mod.github, "discover", boom)
    assert main_mod.main() == 0


def test_main_collects_manual_repo(tmp_path, monkeypatch):
    _stub_stages(monkeypatch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setenv("GITHUB_TOKEN", "gh")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    _write_cfg(tmp_path, "github: {enabled: false}\n")
    (tmp_path / "submit.txt").write_text(
        "https://github.com/foo/bar\n", encoding="utf-8")

    monkeypatch.setattr(main_mod.github, "fetch_repo", lambda t, n: {
        "full_name": n, "html_url": f"https://github.com/{n}",
        "description": "說明", "stargazers_count": 42,
        "pushed_at": "2026-07-01T00:00:00Z", "owner": {"login": "foo"},
        "archived": False, "license": {"spdx_id": "MIT"},
    })
    monkeypatch.setattr(main_mod.github, "fetch_readme", lambda t, n, **k: "README")
    monkeypatch.setattr(main_mod.github, "fetch_scorecard", lambda n: 5.5)

    assert main_mod.main() == 0
    conn = main_mod.db.connect(tmp_path / "videos.db")
    assert main_mod.db.video_exists(conn, "gh_foo_bar")


def test_main_manual_repo_skips_already_collected(tmp_path, monkeypatch):
    _stub_stages(monkeypatch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setenv("GITHUB_TOKEN", "gh")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    _write_cfg(tmp_path, "github: {enabled: false}\n")
    (tmp_path / "submit.txt").write_text(
        "https://github.com/foo/bar\n", encoding="utf-8")

    conn = main_mod.db.connect(tmp_path / "videos.db")
    item = {"video_id": "gh_foo_bar", "title": "foo/bar", "channel": "foo",
            "description": "x", "published_at": "", "thumbnail_url": "",
            "duration_seconds": 0, "view_count": 1,
            "url": "https://github.com/foo/bar", "content_type": "repo"}
    main_mod.db.insert_video(conn, item)

    # 用記錄呼叫取代直接 raise：手動專案階段包在 except Exception 內，
    # 若 stub 直接拋 AssertionError 會被整個吞掉，測試會變成恆真。
    calls = []
    monkeypatch.setattr(main_mod.github, "fetch_repo",
                        lambda t, n: calls.append(n) or None)
    assert main_mod.main() == 0
    assert calls == []          # 已收錄過不應再查 API


def test_main_manual_repo_fetch_failure_skipped(tmp_path, monkeypatch):
    _stub_stages(monkeypatch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.setenv("GITHUB_TOKEN", "gh")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    _write_cfg(tmp_path, "github: {enabled: false}\n")
    (tmp_path / "submit.txt").write_text(
        "https://github.com/bad/repo\n", encoding="utf-8")

    monkeypatch.setattr(main_mod.github, "fetch_repo", lambda t, n: None)
    stages = []
    monkeypatch.setattr(main_mod.generator, "generate",
                        lambda *a, **k: stages.append("generate") or 0)
    monkeypatch.setattr(main_mod.publisher, "publish",
                        lambda *a, **k: stages.append("publish") or False)

    assert main_mod.main() == 0
    assert stages == ["generate", "publish"]     # 抓不到不得中斷後續


def test_main_manual_repo_without_token_warns(tmp_path, monkeypatch):
    """沒有 GITHUB_TOKEN 時略過手動專案，但其他階段照跑。"""
    _stub_stages(monkeypatch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt")
    monkeypatch.setenv("GEMINI_API_KEY", "gm")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    _write_cfg(tmp_path, "github: {enabled: false}\n")
    (tmp_path / "submit.txt").write_text(
        "https://github.com/foo/bar\n", encoding="utf-8")

    # 同上：記錄呼叫而非 raise，避免 except Exception 把恆真測試藏起來。
    calls = []
    monkeypatch.setattr(main_mod.github, "fetch_repo",
                        lambda t, n: calls.append(n) or None)
    assert main_mod.main() == 0
    assert calls == []          # 沒 token 不應查 API
