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


def test_safe_err_masks_api_key():
    msg = collector._safe_err(
        Exception("404 for url: https://x/videos?part=id&key=AIzaSECRET123&q=a")
    )
    assert "AIzaSECRET123" not in msg
    assert "key=***" in msg


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
            make_video(i, duration_seconds=600 if i == "new1" else 60)
            for i in ids
        ],
    )
    added = collector.collect(conn, "key", ["kw"], "2026-01-01T00:00:00Z")
    assert added == 1
    assert db.video_exists(conn, "new1")
    assert not db.video_exists(conn, "short1")


def test_fetch_channel_video_ids(monkeypatch):
    calls = []
    responses = iter([
        # 第一步：channels.list 回傳上傳清單 ID
        FakeResp({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUabc"}}}]}),
        # 第二步：playlistItems.list 回傳影片
        FakeResp({"items": [
            {"contentDetails": {"videoId": "c1"}},
            {"contentDetails": {"videoId": "c2"}},
            {"contentDetails": {}},  # 缺 videoId 要略過
        ]}),
    ])

    def fake_get(url, params=None, **k):
        calls.append((url, params or {}))
        return next(responses)

    monkeypatch.setattr(collector.requests, "get", fake_get)
    assert collector.fetch_channel_video_ids("key", "@test") == ["c1", "c2"]
    assert calls[0][1]["forHandle"] == "@test"          # 第一步用 handle 查頻道
    assert calls[1][1]["playlistId"] == "UUabc"          # 第二步查上傳清單


def test_fetch_channel_video_ids_missing_uploads(monkeypatch):
    # 頻道存在但缺 relatedPlaylists 結構：應回傳空清單而非炸掉
    monkeypatch.setattr(
        collector.requests, "get",
        lambda *a, **k: FakeResp({"items": [{"contentDetails": {}}]}),
    )
    assert collector.fetch_channel_video_ids("key", "@broken") == []


def test_fetch_channel_video_ids_unknown_handle(monkeypatch):
    monkeypatch.setattr(collector.requests, "get", lambda *a, **k: FakeResp({"items": []}))
    assert collector.fetch_channel_video_ids("key", "@notexist") == []


def test_collect_includes_channel_videos(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    db.insert_video(conn, make_video("existing"))
    monkeypatch.setattr(
        collector, "fetch_channel_video_ids",
        lambda key, ch, mr: ["existing", "ch1"],
    )
    monkeypatch.setattr(
        collector, "fetch_video_details",
        lambda key, ids: [make_video(i, duration_seconds=600) for i in ids],
    )
    added = collector.collect(conn, "key", [], "2026-01-01T00:00:00Z",
                              channels=["@test"])
    assert added == 1
    assert db.video_exists(conn, "ch1")


def test_collect_channel_failure_does_not_abort(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")

    def fail_channel(key, ch, mr):
        if ch == "@壞頻道":
            raise collector.requests.ConnectionError("網路錯誤")
        return ["ok1"]

    monkeypatch.setattr(collector, "fetch_channel_video_ids", fail_channel)
    monkeypatch.setattr(
        collector, "fetch_video_details",
        lambda key, ids: [make_video(i, duration_seconds=600) for i in ids],
    )
    added = collector.collect(conn, "key", [], "2026-01-01T00:00:00Z",
                              channels=["@壞頻道", "@好頻道"])
    assert added == 1


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
    monkeypatch.setattr(collector, "fetch_video_details", lambda key, ids: [])
    with pytest.raises(RuntimeError):
        collector.collect(conn, "key", ["kw1", "kw2"], "2026-01-01T00:00:00Z")


def test_collect_keywords_failed_but_channel_videos_saved(tmp_path, monkeypatch):
    """關鍵字全失敗仍要擲例外（保護水位），但頻道影片必須先入庫不得丟失。"""
    conn = db.connect(tmp_path / "t.db")

    def always_fail(*a, **k):
        raise collector.requests.ConnectionError("網路未連線")

    monkeypatch.setattr(collector, "search_videos", always_fail)
    monkeypatch.setattr(
        collector, "fetch_channel_video_ids", lambda key, ch, mr: ["ch1"],
    )
    monkeypatch.setattr(
        collector, "fetch_video_details",
        lambda key, ids: [make_video(i, duration_seconds=600) for i in ids],
    )
    with pytest.raises(RuntimeError):
        collector.collect(conn, "key", ["kw1"], "2026-01-01T00:00:00Z",
                          channels=["@test"])
    assert db.video_exists(conn, "ch1")


def test_collect_extra_ids_bypass_duration_filter(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    monkeypatch.setattr(collector, "search_videos", lambda *a, **k: [])
    monkeypatch.setattr(
        collector, "fetch_video_details",
        lambda key, ids: [make_video(i, duration_seconds=30) for i in ids],
    )
    added = collector.collect(conn, "key", [], "2026-01-01T00:00:00Z",
                              extra_ids=["short_sub1"])
    assert added == 1                          # 30 秒仍收錄
    assert db.video_exists(conn, "short_sub1")


def test_collect_extra_ids_skip_existing(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    db.insert_video(conn, make_video("dup1"))
    monkeypatch.setattr(collector, "search_videos", lambda *a, **k: [])
    monkeypatch.setattr(
        collector, "fetch_video_details",
        lambda key, ids: [make_video(i, duration_seconds=600) for i in ids],
    )
    added = collector.collect(conn, "key", [], "2026-01-01T00:00:00Z",
                              extra_ids=["dup1"])
    assert added == 0
