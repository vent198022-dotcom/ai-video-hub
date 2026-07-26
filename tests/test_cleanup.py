"""失效影片清理測試。"""
from conftest import make_video

import cleanup
import db


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _live(tmp_path, *ids):
    conn = db.connect(tmp_path / "t.db")
    for i in ids:
        db.insert_video(conn, make_video(i))
        db.update_classification(conn, i, True, "工具教學", "摘要", [])
    return conn


def test_removes_deleted_and_private(tmp_path, monkeypatch):
    conn = _live(tmp_path, "keep1", "gone1", "private1")
    payload = {"items": [
        {"id": "keep1", "status": {"privacyStatus": "public"}},
        {"id": "private1", "status": {"privacyStatus": "private"}},
        # gone1 不在回應中 → 已刪除
    ]}
    monkeypatch.setattr(cleanup.requests, "get", lambda *a, **k: FakeResp(payload))
    assert cleanup.remove_dead_videos(conn, "key") == 2
    assert [v["video_id"] for v in db.get_site_videos(conn)] == ["keep1"]


def test_no_videos_no_request(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")

    def boom(*a, **k):
        raise AssertionError("不應發出請求")
    monkeypatch.setattr(cleanup.requests, "get", boom)
    assert cleanup.remove_dead_videos(conn, "key") == 0


def test_api_failure_marks_nothing(tmp_path, monkeypatch):
    conn = _live(tmp_path, "v1", "v2")

    def boom(*a, **k):
        raise cleanup.requests.ConnectionError("網路錯誤")
    monkeypatch.setattr(cleanup.requests, "get", boom)
    assert cleanup.remove_dead_videos(conn, "key") == 0
    assert len(db.get_site_videos(conn)) == 2  # 一部都不能被誤刪
