"""難易度與國內外補標腳本測試（不打真實 API）。"""
from conftest import make_video

import db
import tag_metadata


def test_build_prompt_contains_levels_and_items():
    items = [{"video_id": "v1", "title": "標題一", "category": "工具教學",
              "summary": "摘要一"}]
    p = tag_metadata.build_prompt(items)
    assert "入門" in p and "進階" in p and "專家" in p
    assert "v1" in p and "標題一" in p and "摘要一" in p


def test_build_prompt_asks_both_fields():
    p = tag_metadata.build_prompt([{"video_id": "v1", "title": "標題",
                                    "category": "工具教學", "summary": "摘要"}])
    assert "difficulty" in p and "region" in p
    assert "入門" in p and "國內" in p


def test_build_prompt_omits_body_text():
    """只送標題與摘要，不得夾帶正文（那會讓批次塞不下 100 筆）。"""
    items = [{"video_id": "v1", "title": "標題", "category": "工具教學",
              "summary": "摘要", "description": "超長正文" * 500}]
    p = tag_metadata.build_prompt(items)
    assert "超長正文" not in p


def test_tag_batch_maps_ids(monkeypatch):
    monkeypatch.setattr(tag_metadata, "call_gemini", lambda *a, **k:
                        '[{"video_id":"v1","difficulty":"入門","region":"國內"},'
                        ' {"video_id":"v2","difficulty":"專家","region":"國外"}]')
    out = tag_metadata.tag_batch("k", "m", [{"video_id": "v1"}, {"video_id": "v2"}])
    assert out == {"v1": {"difficulty": "入門", "region": "國內"},
                   "v2": {"difficulty": "專家", "region": "國外"}}


def test_tag_batch_returns_both_fields(monkeypatch):
    monkeypatch.setattr(tag_metadata, "call_gemini", lambda *a, **k:
                        '[{"video_id":"v1","difficulty":"入門","region":"國內"}]')
    assert tag_metadata.tag_batch("k", "m", [{"video_id": "v1"}]) == {
        "v1": {"difficulty": "入門", "region": "國內"}}


def test_tag_batch_drops_invalid_levels(monkeypatch):
    """單一欄位不合法時，僅捨棄該欄位，另一欄位若合法仍保留。"""
    monkeypatch.setattr(tag_metadata, "call_gemini", lambda *a, **k:
                        '[{"video_id":"v1","difficulty":"宇宙級","region":"國內"},'
                        ' {"video_id":"v2","difficulty":"進階","region":"火星"}]')
    out = tag_metadata.tag_batch("k", "m", [{"video_id": "v1"}, {"video_id": "v2"}])
    assert out == {"v1": {"region": "國內"}, "v2": {"difficulty": "進階"}}


def test_tag_batch_drops_invalid_values(monkeypatch):
    monkeypatch.setattr(tag_metadata, "call_gemini", lambda *a, **k:
                        '[{"video_id":"v1","difficulty":"宇宙級","region":"火星"}]')
    assert tag_metadata.tag_batch("k", "m", [{"video_id": "v1"}]) == {"v1": {}}


def test_tag_batch_bad_json_returns_empty(monkeypatch):
    monkeypatch.setattr(tag_metadata, "call_gemini", lambda *a, **k: "不是 JSON")
    assert tag_metadata.tag_batch("k", "m", [{"video_id": "v1"}]) == {}


def _seed(tmp_path, n):
    conn = db.connect(tmp_path / "t.db")
    for i in range(n):
        vid = f"v{i}"
        db.insert_video(conn, make_video(vid))
        db.update_classification(conn, vid, True, "工具教學", "摘要", [])
    return conn


def test_pending_items_only_untagged(tmp_path):
    conn = _seed(tmp_path, 3)
    db.set_difficulty(conn, "v0", "入門")
    db.set_region(conn, "v0", "國內")          # v0 兩個欄位都齊了，才算補標完成
    items = tag_metadata.pending_items(conn)
    assert [i["video_id"] for i in items] == ["v1", "v2"]


def test_pending_items_includes_missing_region(tmp_path):
    conn = _seed(tmp_path, 2)
    db.set_difficulty(conn, "v0", "入門")
    db.set_region(conn, "v0", "國內")          # v0 兩個都齊了
    db.set_difficulty(conn, "v1", "入門")      # v1 缺 region
    assert [i["video_id"] for i in tag_metadata.pending_items(conn)] == ["v1"]


def test_run_tags_all_and_returns_count(tmp_path, monkeypatch):
    conn = _seed(tmp_path, 2)
    monkeypatch.setattr(tag_metadata, "tag_batch",
                        lambda k, m, items: {i["video_id"]: {"difficulty": "進階", "region": "國內"}
                                             for i in items})
    n = tag_metadata.run(conn, "k", "m", batch_size=10, pause_seconds=0)
    assert n == 2
    assert all(v["difficulty"] == "進階" and v["region"] == "國內"
               for v in db.get_site_videos(conn))


def test_run_writes_both_fields(tmp_path, monkeypatch):
    conn = _seed(tmp_path, 1)
    monkeypatch.setattr(tag_metadata, "tag_batch", lambda k, m, items: {
        "v0": {"difficulty": "進階", "region": "國外"}})
    n = tag_metadata.run(conn, "k", "m", batch_size=10, pause_seconds=0)
    assert n == 1
    v = db.get_site_videos(conn)[0]
    assert v["difficulty"] == "進階" and v["region"] == "國外"


def test_run_batch_failure_continues(tmp_path, monkeypatch):
    conn = _seed(tmp_path, 4)
    calls = {"n": 0}

    def flaky(k, m, items):
        calls["n"] += 1
        if calls["n"] == 1:
            return {}                      # 第一批失敗
        return {i["video_id"]: {"difficulty": "入門", "region": "國內"}
                for i in items}

    monkeypatch.setattr(tag_metadata, "tag_batch", flaky)
    n = tag_metadata.run(conn, "k", "m", batch_size=2, pause_seconds=0)
    assert calls["n"] == 2                 # 第一批失敗仍繼續跑第二批
    assert n == 2
