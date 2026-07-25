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
