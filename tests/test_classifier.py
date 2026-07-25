"""classifier 模組測試（不打真實 API，一律 mock）。"""
import requests as requests_lib

from conftest import make_video

import classifier
import db

CATS = ["入門觀念", "提示詞技巧", "工具教學"]


def test_build_prompt_contains_categories_and_ids():
    prompt = classifier.build_prompt([make_video("v1", title="標題一")], CATS)
    assert "工具教學" in prompt
    assert "v1" in prompt
    assert "標題一" in prompt


def test_build_prompt_requires_chinese_language():
    prompt = classifier.build_prompt([make_video("v1")], CATS)
    assert "中文" in prompt
    assert "繁體或簡體" in prompt
    assert "非中文影片一律不相關" in prompt


def test_parse_response_plain_json():
    assert classifier.parse_response('[{"video_id": "a"}]') == [{"video_id": "a"}]


def test_parse_response_markdown_fenced():
    text = '```json\n[{"video_id": "a"}]\n```'
    assert classifier.parse_response(text) == [{"video_id": "a"}]


def test_parse_response_not_array_raises():
    try:
        classifier.parse_response('{"video_id": "a"}')
        assert False, "應該要 raise ValueError"
    except ValueError:
        pass


def _setup(tmp_path, *ids):
    conn = db.connect(tmp_path / "t.db")
    for i in ids:
        db.insert_video(conn, make_video(i))
    return conn


def test_classify_pending_success(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1", "v2")
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "v1", "is_relevant": True, "category": "工具教學",
         "summary": "教你使用 ChatGPT", "tags": ["ChatGPT"]},
        {"video_id": "v2", "is_relevant": False, "category": None,
         "summary": "", "tags": []},
    ])
    ok, skip, fail = classifier.classify_pending(conn, "key", "model", CATS)
    assert (ok, skip, fail) == (1, 1, 0)
    assert db.get_site_videos(conn)[0]["video_id"] == "v1"
    assert len(db.get_videos_by_status(conn, "excluded")) == 1


def test_classify_pending_invalid_category_marks_failed(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1")
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "v1", "is_relevant": True, "category": "自創的分類",
         "summary": "x", "tags": []},
    ])
    ok, skip, fail = classifier.classify_pending(conn, "key", "model", CATS)
    assert (ok, skip, fail) == (0, 0, 1)
    assert len(db.get_videos_by_status(conn, "failed")) == 1


def test_classify_pending_api_error_marks_batch_failed(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1", "v2")

    def boom(*a, **k):
        raise requests_lib.ConnectionError("API 掛了")
    monkeypatch.setattr(classifier, "classify_batch", boom)
    ok, skip, fail = classifier.classify_pending(conn, "key", "model", CATS)
    assert (ok, skip, fail) == (0, 0, 2)
    assert len(db.get_videos_by_status(conn, "failed")) == 2


def test_classify_pending_retries_failed_pool(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1")
    db.mark_failed(conn, "v1")
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "v1", "is_relevant": True, "category": "工具教學",
         "summary": "摘要", "tags": []},
    ])
    ok, skip, fail = classifier.classify_pending(conn, "key", "model", CATS)
    assert (ok, skip, fail) == (1, 0, 0)


def test_classify_pending_missing_result_marks_failed(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1", "v2")
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "v1", "is_relevant": True, "category": "工具教學",
         "summary": "摘要", "tags": []},
        # v2 沒有回傳結果
    ])
    ok, skip, fail = classifier.classify_pending(conn, "key", "model", CATS)
    assert (ok, skip, fail) == (1, 0, 1)
