"""db 模組測試。"""
from conftest import make_video

import db


def _conn(tmp_path):
    return db.connect(tmp_path / "test.db")


def test_insert_and_exists(tmp_path):
    conn = _conn(tmp_path)
    assert not db.video_exists(conn, "abc123")
    db.insert_video(conn, make_video())
    assert db.video_exists(conn, "abc123")


def test_new_video_is_pending(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    rows = db.get_videos_by_status(conn, "pending")
    assert len(rows) == 1
    assert rows[0]["video_id"] == "abc123"
    assert rows[0]["title"] == "測試影片標題"


def test_duplicate_insert_ignored(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.insert_video(conn, make_video(title="不同標題"))
    rows = db.get_videos_by_status(conn, "pending")
    assert len(rows) == 1
    assert rows[0]["title"] == "測試影片標題"


def test_classification_relevant(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "教你用 AI", ["ChatGPT", "入門"])
    assert db.get_videos_by_status(conn, "pending") == []
    site = db.get_site_videos(conn)
    assert len(site) == 1
    assert site[0]["category"] == "工具教學"
    assert site[0]["tags"] == ["ChatGPT", "入門"]


def test_classification_irrelevant_excluded(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", False, None, "", [])
    assert db.get_site_videos(conn) == []
    assert len(db.get_videos_by_status(conn, "excluded")) == 1


def test_mark_failed_and_retry_pool(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.mark_failed(conn, "abc123")
    assert len(db.get_videos_by_status(conn, "failed")) == 1


def test_meta_roundtrip(tmp_path):
    conn = _conn(tmp_path)
    assert db.get_meta(conn, "last_collect_at") is None
    db.set_meta(conn, "last_collect_at", "2026-07-25T00:00:00Z")
    assert db.get_meta(conn, "last_collect_at") == "2026-07-25T00:00:00Z"
    db.set_meta(conn, "last_collect_at", "2026-07-26T00:00:00Z")
    assert db.get_meta(conn, "last_collect_at") == "2026-07-26T00:00:00Z"


def test_site_videos_sorted_desc(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video("old", published_at="2026-01-01T00:00:00Z"))
    db.insert_video(conn, make_video("new", published_at="2026-07-01T00:00:00Z"))
    for vid in ("old", "new"):
        db.update_classification(conn, vid, True, "工具教學", "摘要", [])
    assert [v["video_id"] for v in db.get_site_videos(conn)] == ["new", "old"]


def test_search_terms_roundtrip(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", ["標籤"],
                             search_terms=["回信", "email", "郵件"])
    site = db.get_site_videos(conn)
    assert site[0]["search_terms"] == ["回信", "email", "郵件"]


def test_search_terms_defaults_empty(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", [])
    assert db.get_site_videos(conn)[0]["search_terms"] == []


def test_mark_removed_hides_from_site(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video("v1"))
    db.insert_video(conn, make_video("v2"))
    for vid in ("v1", "v2"):
        db.update_classification(conn, vid, True, "工具教學", "摘要", [])
    n = db.mark_removed(conn, ["v1"])
    assert n == 1
    assert [v["video_id"] for v in db.get_site_videos(conn)] == ["v2"]
    assert len(db.get_videos_by_status(conn, "removed")) == 1


def test_mark_removed_empty_list(tmp_path):
    conn = _conn(tmp_path)
    assert db.mark_removed(conn, []) == 0


def test_migration_adds_column_to_existing_db(tmp_path):
    """模擬舊版資料庫（無 search_terms 欄位），connect 應自動補欄位且不損失資料。"""
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(str(path))
    old.executescript("""
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY, title TEXT NOT NULL, channel TEXT,
            description TEXT, published_at TEXT, thumbnail_url TEXT,
            duration_seconds INTEGER, view_count INTEGER, category TEXT,
            summary TEXT, tags TEXT, status TEXT NOT NULL DEFAULT 'pending',
            collected_at TEXT);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO videos (video_id, title, status, category, summary, tags)
        VALUES ('old1', '舊影片', 'classified', '工具教學', '舊摘要', '[]');
    """)
    old.commit()
    old.close()

    conn = db.connect(path)
    site = db.get_site_videos(conn)
    assert len(site) == 1
    assert site[0]["title"] == "舊影片"
    assert site[0]["search_terms"] == []


def test_insert_defaults_to_video_type(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", [])
    v = db.get_site_videos(conn)[0]
    assert v["content_type"] == "video"
    assert v["url"] is None


def test_insert_article_with_url(tmp_path):
    conn = _conn(tmp_path)
    item = make_video("art_abc")
    item["content_type"] = "article"
    item["url"] = "https://example.com/post"
    db.insert_video(conn, item)
    db.update_classification(conn, "art_abc", True, "工具教學", "摘要", [])
    v = db.get_site_videos(conn)[0]
    assert v["content_type"] == "article"
    assert v["url"] == "https://example.com/post"


def test_migration_adds_content_type_to_existing_db(tmp_path):
    """舊資料庫（無 content_type／url）遷移後，既有列預設為 video。"""
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(str(path))
    old.executescript("""
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY, title TEXT NOT NULL, channel TEXT,
            description TEXT, published_at TEXT, thumbnail_url TEXT,
            duration_seconds INTEGER, view_count INTEGER, category TEXT,
            summary TEXT, tags TEXT, search_terms TEXT,
            status TEXT NOT NULL DEFAULT 'pending', collected_at TEXT);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO videos (video_id, title, status, category, summary, tags)
        VALUES ('old1', '舊影片', 'classified', '工具教學', '舊摘要', '[]');
    """)
    old.commit()
    old.close()

    conn = db.connect(path)
    v = db.get_site_videos(conn)[0]
    assert v["title"] == "舊影片"
    assert v["content_type"] == "video"
    assert v["url"] is None


def test_difficulty_roundtrip(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", [],
                             difficulty="進階")
    assert db.get_site_videos(conn)[0]["difficulty"] == "進階"


def test_difficulty_defaults_none(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", [])
    assert db.get_site_videos(conn)[0]["difficulty"] is None


def test_invalid_difficulty_stored_as_null(tmp_path):
    """AI 亂回難易度時存 NULL，但影片仍要正常上架。"""
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", [],
                             difficulty="超級難")
    site = db.get_site_videos(conn)
    assert len(site) == 1                    # 仍然上架
    assert site[0]["difficulty"] is None


def test_set_difficulty(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", [])
    assert db.set_difficulty(conn, "abc123", "入門") is True
    assert db.get_site_videos(conn)[0]["difficulty"] == "入門"


def test_set_difficulty_rejects_invalid(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", [])
    assert db.set_difficulty(conn, "abc123", "地獄級") is False
    assert db.get_site_videos(conn)[0]["difficulty"] is None


def test_migration_adds_difficulty(tmp_path):
    """舊資料庫（無 difficulty 欄位）遷移後既有列為 NULL 且資料不損。"""
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(str(path))
    old.executescript("""
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY, title TEXT NOT NULL, channel TEXT,
            description TEXT, published_at TEXT, thumbnail_url TEXT,
            duration_seconds INTEGER, view_count INTEGER, category TEXT,
            summary TEXT, tags TEXT, search_terms TEXT, url TEXT,
            content_type TEXT NOT NULL DEFAULT 'video',
            status TEXT NOT NULL DEFAULT 'pending', collected_at TEXT);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO videos (video_id, title, status, category, summary, tags)
        VALUES ('old1', '舊影片', 'classified', '工具教學', '舊摘要', '[]');
    """)
    old.commit()
    old.close()

    conn = db.connect(path)
    v = db.get_site_videos(conn)[0]
    assert v["title"] == "舊影片"
    assert v["difficulty"] is None


def test_region_roundtrip(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", [],
                             region="國內")
    assert db.get_site_videos(conn)[0]["region"] == "國內"


def test_invalid_region_stored_as_null_but_still_published(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", [],
                             region="火星")
    site = db.get_site_videos(conn)
    assert len(site) == 1
    assert site[0]["region"] is None


def test_set_region(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", [])
    assert db.set_region(conn, "abc123", "國外") is True
    assert db.get_site_videos(conn)[0]["region"] == "國外"
    assert db.set_region(conn, "abc123", "外太空") is False
    assert db.get_site_videos(conn)[0]["region"] == "國外"   # 不得被覆寫


def test_insert_repo_content_type(tmp_path):
    conn = _conn(tmp_path)
    item = make_video("repo_x")
    item["content_type"] = "repo"
    item["url"] = "https://github.com/foo/bar"
    db.insert_video(conn, item)
    db.update_classification(conn, "repo_x", True, "開源工具", "摘要", [])
    v = db.get_site_videos(conn)[0]
    assert v["content_type"] == "repo"
    assert v["url"] == "https://github.com/foo/bar"


def test_migration_adds_region(tmp_path):
    """舊資料庫（無 region）遷移後既有列為 NULL 且資料不損。"""
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(str(path))
    old.executescript("""
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY, title TEXT NOT NULL, channel TEXT,
            description TEXT, published_at TEXT, thumbnail_url TEXT,
            duration_seconds INTEGER, view_count INTEGER, category TEXT,
            summary TEXT, tags TEXT, search_terms TEXT, url TEXT,
            content_type TEXT NOT NULL DEFAULT 'video', difficulty TEXT,
            status TEXT NOT NULL DEFAULT 'pending', collected_at TEXT);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO videos (video_id, title, status, category, summary, tags, difficulty)
        VALUES ('old1', '舊影片', 'classified', '工具教學', '舊摘要', '[]', '入門');
    """)
    old.commit()
    old.close()

    conn = db.connect(path)
    v = db.get_site_videos(conn)[0]
    assert v["title"] == "舊影片"
    assert v["difficulty"] == "入門"
    assert v["region"] is None


def test_insert_repo_with_license_and_score(tmp_path):
    conn = _conn(tmp_path)
    item = make_video("gh_a_b")
    item.update({"content_type": "repo", "url": "https://github.com/a/b",
                 "license": "MIT", "security_score": 7.4})
    db.insert_video(conn, item)
    db.update_classification(conn, "gh_a_b", True, "開源工具", "摘要", [])
    v = db.get_site_videos(conn)[0]
    assert v["license"] == "MIT"
    assert v["security_score"] == 7.4


def test_insert_defaults_license_and_score_null(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video())
    db.update_classification(conn, "abc123", True, "工具教學", "摘要", [])
    v = db.get_site_videos(conn)[0]
    assert v["license"] is None
    assert v["security_score"] is None


def test_safety_roundtrip_and_invalid(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video("s1"))
    db.update_classification(conn, "s1", True, "工具教學", "摘要", [], safety="安全")
    assert db.get_site_videos(conn)[0]["safety"] == "安全"
    db.insert_video(conn, make_video("s2"))
    db.update_classification(conn, "s2", True, "工具教學", "摘要", [], safety="超危險")
    got = {v["video_id"]: v["safety"] for v in db.get_site_videos(conn)}
    assert got["s2"] is None          # 非法值存 NULL
    assert len(got) == 2              # 但仍然上架


def test_migration_adds_safety_columns(tmp_path):
    """舊資料庫遷移後三個新欄位皆為 NULL 且既有資料不損。"""
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(str(path))
    old.executescript("""
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY, title TEXT NOT NULL, channel TEXT,
            description TEXT, published_at TEXT, thumbnail_url TEXT,
            duration_seconds INTEGER, view_count INTEGER, category TEXT,
            summary TEXT, tags TEXT, search_terms TEXT, url TEXT,
            content_type TEXT NOT NULL DEFAULT 'video', difficulty TEXT,
            region TEXT, status TEXT NOT NULL DEFAULT 'pending',
            collected_at TEXT);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO videos (video_id, title, status, category, summary, tags,
                            difficulty, region)
        VALUES ('old1', '舊影片', 'classified', '工具教學', '摘要', '[]', '入門', '國內');
    """)
    old.commit()
    old.close()
    conn = db.connect(path)
    v = db.get_site_videos(conn)[0]
    assert v["title"] == "舊影片" and v["region"] == "國內"
    assert v["license"] is None and v["security_score"] is None and v["safety"] is None


def _classified(conn, *ids):
    for i in ids:
        db.insert_video(conn, make_video(i))
        db.update_classification(conn, i, True, "工具教學", "摘要", [])


def test_drop_items_hides_from_site(tmp_path):
    conn = _conn(tmp_path)
    _classified(conn, "v1", "v2")
    assert db.drop_items(conn, ["v1"]) == 1
    assert [v["video_id"] for v in db.get_site_videos(conn)] == ["v2"]
    assert len(db.get_videos_by_status(conn, "dropped")) == 1


def test_drop_items_empty_list(tmp_path):
    conn = _conn(tmp_path)
    assert db.drop_items(conn, []) == 0


def test_drop_items_idempotent(tmp_path):
    conn = _conn(tmp_path)
    _classified(conn, "v1")
    assert db.drop_items(conn, ["v1"]) == 1
    assert db.drop_items(conn, ["v1"]) == 0      # 已下架者不重複計數


def test_drop_items_unknown_id_is_noop(tmp_path):
    conn = _conn(tmp_path)
    _classified(conn, "v1")
    assert db.drop_items(conn, ["不存在"]) == 0
    assert len(db.get_site_videos(conn)) == 1


def test_drop_also_affects_pending(tmp_path):
    """尚未分類的項目也要能下架，否則它之後會自己冒出來。"""
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video("p1"))
    assert db.drop_items(conn, ["p1"]) == 1
    assert db.get_videos_by_status(conn, "pending") == []


def test_restore_dropped_returns_classified(tmp_path):
    conn = _conn(tmp_path)
    _classified(conn, "v1", "v2")
    db.drop_items(conn, ["v1", "v2"])
    assert db.restore_dropped(conn, ["v2"]) == 1        # v2 仍在清單內，只復原 v1
    site = [v["video_id"] for v in db.get_site_videos(conn)]
    assert site == ["v1"]
    assert len(db.get_videos_by_status(conn, "dropped")) == 1


def test_restore_dropped_unclassified_goes_to_pending(tmp_path):
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video("p1"))            # 從未分類，沒有 category
    db.drop_items(conn, ["p1"])
    assert db.restore_dropped(conn, []) == 1
    assert [v["video_id"] for v in db.get_videos_by_status(conn, "pending")] == ["p1"]


def test_restore_dropped_empty_keep_restores_all(tmp_path):
    conn = _conn(tmp_path)
    _classified(conn, "v1", "v2")
    db.drop_items(conn, ["v1", "v2"])
    assert db.restore_dropped(conn, []) == 2
    assert len(db.get_site_videos(conn)) == 2


def test_restore_dropped_does_not_touch_other_statuses(tmp_path):
    """excluded／removed 是不同原因造成的，不得被復原邏輯誤改。"""
    conn = _conn(tmp_path)
    db.insert_video(conn, make_video("e1"))
    db.update_classification(conn, "e1", False, None, "", [])   # excluded
    _classified(conn, "r1")
    db.mark_removed(conn, ["r1"])                                # removed
    assert db.restore_dropped(conn, []) == 0
    assert len(db.get_videos_by_status(conn, "excluded")) == 1
    assert len(db.get_videos_by_status(conn, "removed")) == 1
