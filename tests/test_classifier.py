"""classifier 模組測試（不打真實 API，一律 mock）。"""
import pytest
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
    assert "非中文內容、純新聞、廣告、閒聊一律不相關" in prompt


def test_classify_batch_key_in_header_not_url(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        captured["url"] = url

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}
        return R()

    monkeypatch.setattr(classifier.requests, "post", fake_post)
    classifier.classify_batch("secret-key", "m", [make_video("v1")], CATS)
    assert captured["headers"]["x-goog-api-key"] == "secret-key"
    assert "secret-key" not in captured["url"]
    assert "key" not in (captured.get("params") or {})


def test_classify_pending_paces_batches(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1", "v2")
    sleeps = []
    monkeypatch.setattr(classifier.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [])
    classifier.classify_pending(conn, "k", "m", CATS, batch_size=1, pause_seconds=7)
    assert sleeps == [7]  # 兩批之間恰好停一次


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


def test_build_prompt_includes_transcript_when_present():
    v = make_video("v1")
    v["transcript"] = "這是字幕逐字稿內容"
    prompt = classifier.build_prompt([v], CATS)
    assert "這是字幕逐字稿內容" in prompt
    assert "search_terms" in prompt


def test_build_prompt_omits_empty_transcript():
    prompt = classifier.build_prompt([make_video("v1")], CATS)
    assert "transcript" not in prompt


def test_build_prompt_gives_articles_full_body():
    v = make_video("art_1", description="正" * 2000)
    v["content_type"] = "article"
    prompt = classifier.build_prompt([v], CATS)
    assert prompt.count("正") > 1000        # 文章用長版正文，不是 300 字截斷


def test_build_prompt_keeps_video_description_short():
    v = make_video("v1", description="甲" * 2000)
    prompt = classifier.build_prompt([v], CATS)
    assert prompt.count("甲") == 300        # 影片維持 300 字


def test_classify_pending_fetches_and_stores_search_terms(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1")
    seen = {}

    def fake_batch(api_key, model, videos, categories):
        seen["transcript"] = videos[0].get("transcript")
        return [{"video_id": "v1", "is_relevant": True, "category": "工具教學",
                 "summary": "深度摘要", "tags": ["t"],
                 "search_terms": ["回信", "email"]}]

    monkeypatch.setattr(classifier, "classify_batch", fake_batch)
    classifier.classify_pending(conn, "k", "m", CATS,
                                transcript_fn=lambda vid: f"字幕-{vid}")
    assert seen["transcript"] == "字幕-v1"
    assert db.get_site_videos(conn)[0]["search_terms"] == ["回信", "email"]


def test_classify_pending_skips_transcript_fn_for_articles(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    v_video = make_video("v1")
    v_article = make_video("art1")
    v_article["content_type"] = "article"
    db.insert_video(conn, v_video)
    db.insert_video(conn, v_article)

    called = []

    def fake_transcript_fn(vid):
        called.append(vid)
        return f"字幕-{vid}"

    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "v1", "is_relevant": True, "category": "工具教學",
         "summary": "摘要", "tags": [], "search_terms": []},
        {"video_id": "art1", "is_relevant": True, "category": "工具教學",
         "summary": "摘要", "tags": [], "search_terms": []},
    ])
    classifier.classify_pending(conn, "k", "m", CATS, batch_size=10,
                                transcript_fn=fake_transcript_fn)
    assert called == ["v1"]


def test_classify_pending_without_transcript_fn(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1")
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "v1", "is_relevant": True, "category": "工具教學",
         "summary": "一般摘要", "tags": [], "search_terms": []},
    ])
    ok, skip, fail = classifier.classify_pending(conn, "k", "m", CATS)
    assert (ok, skip, fail) == (1, 0, 0)


def test_build_prompt_asks_for_difficulty():
    prompt = classifier.build_prompt([make_video("v1")], CATS)
    assert "difficulty" in prompt
    assert "入門" in prompt and "進階" in prompt and "專家" in prompt


def test_classify_pending_stores_difficulty(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1")
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "v1", "is_relevant": True, "category": "工具教學",
         "summary": "摘要", "tags": [], "search_terms": [], "difficulty": "專家"},
    ])
    classifier.classify_pending(conn, "k", "m", CATS)
    assert db.get_site_videos(conn)[0]["difficulty"] == "專家"


def test_classify_pending_bad_difficulty_still_publishes(tmp_path, monkeypatch):
    """難易度亂填不得害整筆變成失敗。"""
    conn = _setup(tmp_path, "v1")
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "v1", "is_relevant": True, "category": "工具教學",
         "summary": "摘要", "tags": [], "search_terms": [], "difficulty": "無敵難"},
    ])
    ok, skip, fail = classifier.classify_pending(conn, "k", "m", CATS)
    assert (ok, skip, fail) == (1, 0, 0)
    assert db.get_site_videos(conn)[0]["difficulty"] is None


def test_build_prompt_marks_repo_type():
    v = make_video("gh_a_b", description="English README content")
    v["content_type"] = "repo"
    prompt = classifier.build_prompt([v], CATS)
    assert "repo" in prompt
    assert prompt.count("English README content") == 1


def test_prompt_exempts_repos_from_chinese_rule():
    prompt = classifier.build_prompt([make_video("v1")], CATS)
    assert "開源專案" in prompt          # 語言例外規則有寫進 prompt
    assert "region" in prompt


def test_classify_pending_stores_region(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1")
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "v1", "is_relevant": True, "category": "工具教學",
         "summary": "摘要", "tags": [], "search_terms": [],
         "difficulty": "入門", "region": "國外"},
    ])
    classifier.classify_pending(conn, "k", "m", CATS)
    assert db.get_site_videos(conn)[0]["region"] == "國外"


def test_classify_pending_bad_region_still_publishes(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1")
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "v1", "is_relevant": True, "category": "工具教學",
         "summary": "摘要", "tags": [], "search_terms": [], "region": "外太空"},
    ])
    ok, skip, fail = classifier.classify_pending(conn, "k", "m", CATS)
    assert (ok, skip, fail) == (1, 0, 0)
    assert db.get_site_videos(conn)[0]["region"] is None


def test_prompt_asks_repo_safety():
    prompt = classifier.build_prompt([make_video("v1")], CATS)
    assert "safety" in prompt
    assert "疑慮" in prompt


def test_repo_flagged_unsafe_is_not_published(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    item = make_video("gh_x_y")
    item["content_type"] = "repo"
    db.insert_video(conn, item)
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "gh_x_y", "is_relevant": True, "category": "開源工具",
         "summary": "摘要", "tags": [], "search_terms": [], "safety": "疑慮"},
    ])
    ok, skip, fail = classifier.classify_pending(conn, "k", "m", CATS + ["開源工具"])
    assert (ok, skip, fail) == (0, 1, 0)          # 記為排除而非失敗
    assert db.get_site_videos(conn) == []


def test_repo_marked_safe_is_published(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    item = make_video("gh_ok")
    item["content_type"] = "repo"
    db.insert_video(conn, item)
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "gh_ok", "is_relevant": True, "category": "開源工具",
         "summary": "摘要", "tags": [], "search_terms": [], "safety": "安全"},
    ])
    ok, skip, fail = classifier.classify_pending(conn, "k", "m", CATS + ["開源工具"])
    assert (ok, skip, fail) == (1, 0, 0)
    assert db.get_site_videos(conn)[0]["safety"] == "安全"


def test_non_repo_unaffected_by_safety(tmp_path, monkeypatch):
    """影片即使沒有 safety 欄位也要正常上架。"""
    conn = db.connect(tmp_path / "t.db")
    db.insert_video(conn, make_video("v1"))
    monkeypatch.setattr(classifier, "classify_batch", lambda *a, **k: [
        {"video_id": "v1", "is_relevant": True, "category": "工具教學",
         "summary": "摘要", "tags": [], "search_terms": []},
    ])
    ok, skip, fail = classifier.classify_pending(conn, "k", "m", CATS)
    assert (ok, skip, fail) == (1, 0, 0)


def _http_error(status, body=None):
    """建立帶 response 的 HTTPError，模擬 raise_for_status 擲出的例外。"""
    resp = requests_lib.Response()
    resp.status_code = status
    resp._content = (body if body is not None else "{}").encode("utf-8")
    return requests_lib.HTTPError(f"{status} Error", response=resp)


def _fake_clock(monkeypatch, step=61.0):
    """假時鐘：每讀一次時間前進 step 秒（預設略超過一分鐘），模擬批次之間經過的時間。"""
    now = [0.0]

    def tick():
        now[0] += step
        return now[0]
    monkeypatch.setattr(classifier.time, "monotonic", tick)


_QUOTA_BODY = (
    '{"error": {"code": 429, "message": "You exceeded your current quota.",'
    ' "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",'
    ' "violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_requests",'
    ' "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "20"}]},'
    ' {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "41s"}]}}'
)


def test_error_detail_extracts_quota_info():
    detail = classifier.error_detail(_http_error(429, _QUOTA_BODY))
    assert "429" in detail
    assert "You exceeded your current quota." in detail
    assert "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in detail
    assert "20" in detail
    assert "41s" in detail


def test_error_detail_tolerates_non_json_body():
    assert classifier.error_detail(_http_error(503, "<html>oops</html>")) == "HTTP 503"


def test_error_detail_non_http_error_falls_back_to_str():
    assert "斷線" in classifier.error_detail(requests_lib.ConnectionError("斷線"))


def test_api_error_log_contains_quota_detail(tmp_path, monkeypatch, caplog):
    conn = _setup(tmp_path, "v1")

    def boom(*a, **k):
        raise _http_error(429, _QUOTA_BODY)
    monkeypatch.setattr(classifier, "classify_batch", boom)
    classifier.classify_pending(conn, "k", "m", CATS, pause_seconds=0)
    assert "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in caplog.text


def test_stops_after_consecutive_429(tmp_path, monkeypatch):
    """連續 429 達上限就停，剩下的不再打 API、也不改動狀態。"""
    _fake_clock(monkeypatch)
    conn = _setup(tmp_path, "v1", "v2", "v3", "v4", "v5")
    db.mark_failed(conn, "v5")  # 舊的失敗項，未輪到時應維持 failed
    calls = []

    def quota(api_key, model, videos, categories):
        calls.append([v["video_id"] for v in videos])
        raise _http_error(429)
    monkeypatch.setattr(classifier, "classify_batch", quota)
    ok, skip, fail = classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=2)
    assert len(calls) == 2
    assert (ok, skip, fail) == (0, 0, 2)
    assert {v["video_id"] for v in db.get_videos_by_status(conn, "pending")} == {"v3", "v4"}
    assert {v["video_id"] for v in db.get_videos_by_status(conn, "failed")} == {"v1", "v2", "v5"}


def test_stop_skips_transcript_fetch_for_remaining(tmp_path, monkeypatch):
    _fake_clock(monkeypatch)
    conn = _setup(tmp_path, "v1", "v2", "v3")
    fetched = []

    def quota(*a, **k):
        raise _http_error(429)
    monkeypatch.setattr(classifier, "classify_batch", quota)
    classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=1,
        transcript_fn=lambda vid: fetched.append(vid) or "")
    assert fetched == ["v1"]


def test_non_429_resets_consecutive_count(tmp_path, monkeypatch):
    """429 中間夾了成功或 503，計數歸零，不會提早停止。"""
    _fake_clock(monkeypatch)
    conn = _setup(tmp_path, "v1", "v2", "v3", "v4", "v5", "v6")
    outcomes = iter([429, "ok", 429, 503, 429, "ok"])
    calls = []

    def flaky(api_key, model, videos, categories):
        vid = videos[0]["video_id"]
        calls.append(vid)
        o = next(outcomes)
        if o == "ok":
            return [{"video_id": vid, "is_relevant": False, "category": None,
                     "summary": "", "tags": []}]
        raise _http_error(o)
    monkeypatch.setattr(classifier, "classify_batch", flaky)
    ok, skip, fail = classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=2)
    assert calls == ["v1", "v2", "v3", "v4", "v5", "v6"]
    assert (ok, skip, fail) == (0, 2, 4)


def test_503_does_not_trigger_stop(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1", "v2", "v3")
    calls = []

    def busy(*a, **k):
        calls.append(1)
        raise _http_error(503)
    monkeypatch.setattr(classifier, "classify_batch", busy)
    classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=1)
    assert len(calls) == 3


def test_stop_logs_remaining_count(tmp_path, monkeypatch, caplog):
    _fake_clock(monkeypatch)
    conn = _setup(tmp_path, "v1", "v2", "v3", "v4")

    def quota(*a, **k):
        raise _http_error(429)
    monkeypatch.setattr(classifier, "classify_batch", quota)
    classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=1)
    assert "剩 3 筆" in caplog.text


@pytest.mark.parametrize("body", [
    '[{"error": {}}]', '{"error": "quota"}', '{"error": {"details": ["x"]}}',
    '{"error": {"details": [{"violations": ["x"]}]}}', '{"error": {"details": {"a": 1}}}',
    'null', '"str"',
])
def test_error_detail_never_raises_on_malformed_body(body):
    """error_detail 在 except 區塊裡被呼叫，自己擲例外會打斷整個每日管線。"""
    assert classifier.error_detail(_http_error(429, body)) == "HTTP 429"


def test_error_detail_skips_malformed_detail_entries_but_keeps_the_rest():
    body = ('{"error": {"message": "超出額度", "details": ["x", 3,'
            ' {"violations": ["y", {"quotaId": "PerDay", "quotaValue": "20"}]},'
            ' {"retryDelay": "41s"}]}}')
    assert classifier.error_detail(_http_error(429, body)) == (
        "HTTP 429；超出額度；額度 PerDay（上限 20）；建議等待 41s")


def test_malformed_429_body_still_marks_batch_failed(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1")

    def boom(*a, **k):
        raise _http_error(429, '{"error": "quota"}')
    monkeypatch.setattr(classifier, "classify_batch", boom)
    assert classifier.classify_pending(conn, "k", "m", CATS, pause_seconds=0) == (0, 0, 1)


def test_quick_429_streak_within_a_minute_does_not_stop(tmp_path, monkeypatch):
    """連續 429 若還不到一分鐘，可能只是每分鐘限流，不得判定為額度用盡。"""
    conn = _setup(tmp_path, "v1", "v2", "v3", "v4")
    _fake_clock(monkeypatch, step=5.0)
    outcomes = iter([429, 429, 429, "ok"])

    def rpm(api_key, model, videos, categories):
        vid = videos[0]["video_id"]
        o = next(outcomes)
        if o == "ok":
            return [{"video_id": vid, "is_relevant": False, "category": None,
                     "summary": "", "tags": []}]
        raise _http_error(o)
    monkeypatch.setattr(classifier, "classify_batch", rpm)
    ok, skip, fail = classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=2)
    assert (ok, skip, fail) == (0, 1, 3)


def test_long_429_streak_stops_once_past_a_minute(tmp_path, monkeypatch):
    conn = _setup(tmp_path, *[f"v{i}" for i in range(30)])
    _fake_clock(monkeypatch, step=5.0)
    calls = []

    def quota(*a, **k):
        calls.append(1)
        raise _http_error(429)
    monkeypatch.setattr(classifier, "classify_batch", quota)
    classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=2)
    # 第 1 批 429 時起算（t=5），之後每批判斷時前進 5 秒；第 14 批前滿 60 秒而停止
    assert len(calls) == 13


def test_new_429_streak_restarts_the_clock(tmp_path, monkeypatch):
    """很早之前的一次 429 不得算進後來的新一串，否則每分鐘限流又會被誤判。"""
    conn = _setup(tmp_path, "v1", "v2", "v3", "v4", "v5")
    now = [0.0]
    monkeypatch.setattr(classifier.time, "monotonic", lambda: now[0])
    outcomes = iter([(429, 0), ("ok", 120), (429, 5), (429, 5), ("ok", 5)])
    calls = []

    def flaky(api_key, model, videos, categories):
        calls.append(videos[0]["video_id"])
        o, advance = next(outcomes)
        now[0] += advance
        if o == "ok":
            return []
        raise _http_error(o)
    monkeypatch.setattr(classifier, "classify_batch", flaky)
    classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=2)
    assert calls == ["v1", "v2", "v3", "v4", "v5"]


def test_negative_max_consecutive_429_disables_stop(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1", "v2")

    def quota(*a, **k):
        raise _http_error(429)
    monkeypatch.setattr(classifier, "classify_batch", quota)
    assert classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=-1) == (0, 0, 2)


@pytest.mark.parametrize("limit", [0, None])
def test_max_consecutive_429_zero_or_none_disables_stop(tmp_path, monkeypatch, limit):
    conn = _setup(tmp_path, "v1", "v2", "v3")
    _fake_clock(monkeypatch)
    calls = []

    def quota(*a, **k):
        calls.append(1)
        raise _http_error(429)
    monkeypatch.setattr(classifier, "classify_batch", quota)
    classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=limit)
    assert len(calls) == 3


def test_stop_remaining_count_with_larger_batches(tmp_path, monkeypatch, caplog):
    conn = _setup(tmp_path, *[f"v{i}" for i in range(7)])
    _fake_clock(monkeypatch, step=61.0)

    def quota(*a, **k):
        raise _http_error(429)
    monkeypatch.setattr(classifier, "classify_batch", quota)
    ok, skip, fail = classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=3, pause_seconds=0, max_consecutive_429=1)
    assert fail == 3
    assert "剩 4 筆" in caplog.text
    assert len(db.get_videos_by_status(conn, "pending")) == 4


def test_connection_error_resets_consecutive_count(tmp_path, monkeypatch):
    conn = _setup(tmp_path, "v1", "v2", "v3", "v4")
    _fake_clock(monkeypatch)
    outcomes = iter([429, "conn", 429, "ok"])
    calls = []

    def flaky(api_key, model, videos, categories):
        calls.append(videos[0]["video_id"])
        o = next(outcomes)
        if o == "ok":
            return []
        if o == "conn":
            raise requests_lib.ConnectionError("斷線")
        raise _http_error(o)
    monkeypatch.setattr(classifier, "classify_batch", flaky)
    classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=2)
    assert calls == ["v1", "v2", "v3", "v4"]


def test_partial_success_resets_consecutive_count(tmp_path, monkeypatch):
    """API 有回應但缺項目，仍代表額度可用，計數要歸零。"""
    conn = _setup(tmp_path, "v1", "v2", "v3", "v4")
    _fake_clock(monkeypatch)
    outcomes = iter([429, "partial", 429, "ok"])
    calls = []

    def flaky(api_key, model, videos, categories):
        calls.append(videos[0]["video_id"])
        if next(outcomes) in ("ok", "partial"):
            return []
        raise _http_error(429)
    monkeypatch.setattr(classifier, "classify_batch", flaky)
    classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=2)
    assert calls == ["v1", "v2", "v3", "v4"]


def test_no_stop_warning_when_queue_finishes_on_last_429(tmp_path, monkeypatch, caplog):
    conn = _setup(tmp_path, "v1", "v2")
    _fake_clock(monkeypatch)

    def quota(*a, **k):
        raise _http_error(429)
    monkeypatch.setattr(classifier, "classify_batch", quota)
    classifier.classify_pending(
        conn, "k", "m", CATS, batch_size=1, pause_seconds=0, max_consecutive_429=2)
    assert "停止分類" not in caplog.text


def test_api_key_never_logged_on_429(tmp_path, monkeypatch, caplog):
    conn = _setup(tmp_path, "v1")
    secret = "AIzaUNIQUE-test-key-9f3b"

    def fake_post(url, **kwargs):
        resp = requests_lib.Response()
        resp.status_code = 429
        resp.url = url
        resp._content = _QUOTA_BODY.encode("utf-8")
        return resp
    monkeypatch.setattr(classifier.requests, "post", fake_post)
    classifier.classify_pending(conn, secret, "m", CATS, pause_seconds=0)
    assert "GenerateRequestsPerDay" in caplog.text
    assert secret not in caplog.text
