"""字幕抓取模組測試（不打真實 YouTube）。"""
import transcript


def test_fetch_joins_and_truncates(monkeypatch):
    monkeypatch.setattr(
        transcript, "_raw_segments",
        lambda vid, langs: [{"text": "第一句"}, {"text": "第二句"}, {"text": "第三句"}],
    )
    assert transcript.fetch("v1") == "第一句 第二句 第三句"
    assert transcript.fetch("v1", max_chars=5) == "第一句 第"


def test_fetch_returns_empty_on_error(monkeypatch):
    def boom(vid, langs):
        raise RuntimeError("沒有字幕")
    monkeypatch.setattr(transcript, "_raw_segments", boom)
    assert transcript.fetch("v1") == ""


def test_fetch_returns_empty_on_no_segments(monkeypatch):
    monkeypatch.setattr(transcript, "_raw_segments", lambda vid, langs: [])
    assert transcript.fetch("v1") == ""
