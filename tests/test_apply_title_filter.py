"""apply_title_filter 一次性清理腳本測試。"""
from conftest import make_video

import apply_title_filter
import db


def _seed(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rows = [
        # (id, 標題, 狀態, 型態)
        ("p_zh", "ChatGPT 教學", "pending", "video"),
        ("p_en", "How to use ChatGPT", "pending", "video"),
        ("f_jp", "ChatGPTの使い方", "failed", "video"),
        ("f_yue", "唔識呢5個 AI 秘技", "failed", "video"),
        ("c_yue", "【n8n廣東話教學】自動化", "classified", "video"),
        ("c_en", "Claude Code tutorial", "classified", "video"),
        ("c_jp", "AI 強強聯手｜すごい知識站", "classified", "video"),
        ("c_zh", "NotebookLM 教學", "classified", "video"),
        ("art_en", "English article", "pending", "article"),
        ("repo_en", "owner/repo", "failed", "repo"),
        ("manual_en", "Manually submitted English video", "pending", "video"),
        ("ex_yue", "睇完就識", "excluded", "video"),
    ]
    for vid, title, status, ctype in rows:
        db.insert_video(conn, make_video(vid, title=title, content_type=ctype))
        if status == "failed":
            db.mark_failed(conn, vid)
        elif status == "classified":
            db.update_classification(conn, vid, True, "工具教學", "摘要", [])
        elif status == "excluded":
            db.update_classification(conn, vid, False, None, "", [])
    return conn


def _status(conn):
    return dict(conn.execute("SELECT video_id, status FROM videos"))


def test_backlog_gets_all_rules_published_only_cantonese(tmp_path):
    conn = _seed(tmp_path)
    found = apply_title_filter.apply(conn, protected_ids=["manual_en"], dry_run=False)
    s = _status(conn)
    # 積壓：三種規則都套用
    assert s["p_en"] == s["f_jp"] == s["f_yue"] == "excluded"
    assert s["p_zh"] == "pending"
    # 已上架：只依廣東話規則下架，非中文、日文誤判風險較高的維持上架
    assert s["c_yue"] == "excluded"
    assert s["c_en"] == s["c_jp"] == s["c_zh"] == "classified"
    # 文章、開源專案、人工提交不受影響
    assert s["art_en"] == "pending"
    assert s["repo_en"] == "failed"
    assert s["manual_en"] == "pending"
    assert sorted(found) == ["c_yue", "f_jp", "f_yue", "p_en"]
    assert found["c_yue"] == ("classified", "廣東話")
    assert found["p_en"] == ("pending", "非中文")


def test_dry_run_changes_nothing(tmp_path):
    conn = _seed(tmp_path)
    before = _status(conn)
    found = apply_title_filter.apply(conn, protected_ids=[], dry_run=True)
    assert _status(conn) == before
    assert "manual_en" in found  # 未受保護時，人工提交的英文影片也會被列出


def test_main_protects_videos_listed_in_submit_txt(tmp_path, monkeypatch):
    conn = _seed(tmp_path)
    conn.close()
    (tmp_path / "t.db").rename(tmp_path / "videos.db")
    (tmp_path / "submit.txt").write_text(
        "https://www.youtube.com/watch?v=manual_en\n", encoding="utf-8")
    monkeypatch.setattr(apply_title_filter, "ROOT", tmp_path)
    monkeypatch.setattr(apply_title_filter.submissions, "read_entries",
                        lambda path: (["manual_en"], [], []) if path == tmp_path / "submit.txt"
                        else (_ for _ in ()).throw(AssertionError(path)))
    assert apply_title_filter.main([]) == 0
    s = _status(db.connect(tmp_path / "videos.db"))
    assert s["manual_en"] == "pending"
    assert s["p_en"] == "excluded"


def test_main_dry_run_flag(tmp_path, monkeypatch):
    conn = _seed(tmp_path)
    before = _status(conn)
    conn.close()
    (tmp_path / "t.db").rename(tmp_path / "videos.db")
    monkeypatch.setattr(apply_title_filter, "ROOT", tmp_path)
    monkeypatch.setattr(apply_title_filter.submissions, "read_entries", lambda p: ([], [], []))
    assert apply_title_filter.main(["--dry-run"]) == 0
    assert _status(db.connect(tmp_path / "videos.db")) == before
