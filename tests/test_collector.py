"""collector 模組測試（不打真實 API，一律 mock）。"""
import pytest
from conftest import make_video

import collector
import db


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_parse_duration():
    assert collector.parse_duration("PT1H2M3S") == 3723
    assert collector.parse_duration("PT5M") == 300
    assert collector.parse_duration("PT45S") == 45
    assert collector.parse_duration("") == 0
    assert collector.parse_duration("垃圾字串") == 0


def test_search_videos_extracts_ids(monkeypatch):
    payload = {"items": [
        {"id": {"videoId": "a1"}},
        {"id": {"videoId": "b2"}},
        {"id": {}},  # 缺 videoId 的項目要略過
    ]}
    monkeypatch.setattr(collector.requests, "get", lambda *a, **k: FakeResp(payload))
    ids = collector.search_videos("key", "ChatGPT 教學", "2026-01-01T00:00:00Z")
    assert ids == ["a1", "b2"]


def test_fetch_video_details_maps_fields(monkeypatch):
    payload = {"items": [{
        "id": "a1",
        "snippet": {
            "title": "影片A",
            "channelTitle": "頻道A",
            "description": "描述",
            "publishedAt": "2026-07-01T00:00:00Z",
            "thumbnails": {"medium": {"url": "https://img/a.jpg"}},
        },
        "contentDetails": {"duration": "PT10M"},
        "statistics": {"viewCount": "1234"},
    }]}
    monkeypatch.setattr(collector.requests, "get", lambda *a, **k: FakeResp(payload))
    videos = collector.fetch_video_details("key", ["a1"])
    assert videos == [{
        "video_id": "a1",
        "title": "影片A",
        "channel": "頻道A",
        "description": "描述",
        "published_at": "2026-07-01T00:00:00Z",
        "thumbnail_url": "https://img/a.jpg",
        "duration_seconds": 600,
        "view_count": 1234,
    }]


def test_fetch_video_details_empty_list_no_request(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("不應發出請求")
    monkeypatch.setattr(collector.requests, "get", boom)
    assert collector.fetch_video_details("key", []) == []


def test_collect_skips_existing_and_short(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    db.insert_video(conn, make_video("existing"))

    monkeypatch.setattr(
        collector, "search_videos",
        lambda *a, **k: ["existing", "new1", "short1"],
    )
    monkeypatch.setattr(
        collector, "fetch_video_details",
        lambda key, ids: [
            make_video("new1", duration_seconds=600),
            make_video("short1", duration_seconds=60),
        ],
    )
    added = collector.collect(conn, "key", ["kw"], "2026-01-01T00:00:00Z")
    assert added == 1
    assert db.video_exists(conn, "new1")
    assert not db.video_exists(conn, "short1")


def test_collect_one_keyword_failure_does_not_abort(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    calls = []

    def fake_search(key, kw, *a, **k):
        calls.append(kw)
        if kw == "壞關鍵字":
            raise collector.requests.ConnectionError("網路錯誤")
        return ["ok1"]

    monkeypatch.setattr(collector, "search_videos", fake_search)
    monkeypatch.setattr(
        collector, "fetch_video_details",
        lambda key, ids: [make_video(i, duration_seconds=600) for i in ids],
    )
    added = collector.collect(conn, "key", ["壞關鍵字", "好關鍵字"], "2026-01-01T00:00:00Z")
    assert calls == ["壞關鍵字", "好關鍵字"]
    assert added == 1


def test_collect_all_keywords_failed_raises(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")

    def always_fail(*a, **k):
        raise collector.requests.ConnectionError("網路未連線")

    monkeypatch.setattr(collector, "search_videos", always_fail)
    monkeypatch.setattr(
        collector, "fetch_video_details",
        lambda key, ids: (_ for _ in ()).throw(AssertionError("不應呼叫")),
    )
    with pytest.raises(RuntimeError):
        collector.collect(conn, "key", ["kw1", "kw2"], "2026-01-01T00:00:00Z")
