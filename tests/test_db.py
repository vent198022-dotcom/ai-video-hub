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
