"""手動提交清單解析測試。"""
import submissions


def _write(tmp_path, content):
    p = tmp_path / "submit.txt"
    p.write_text(content, encoding="utf-8")
    return p


def test_parses_all_url_forms(tmp_path):
    p = _write(tmp_path, """
# 這是註解，要略過
https://www.youtube.com/watch?v=aaaaaaaaaaa
https://youtu.be/bbbbbbbbbbb
https://www.youtube.com/shorts/ccccccccccc
https://m.youtube.com/watch?v=ddddddddddd&t=30s

ccccccccccc
""")
    assert submissions.read_ids(p) == [
        "aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc", "ddddddddddd",
    ]


def test_missing_file_returns_empty(tmp_path):
    assert submissions.read_ids(tmp_path / "nope.txt") == []


def test_ignores_unparseable_lines(tmp_path):
    p = _write(tmp_path, "https://example.com/foo\n隨手打的字\n")
    assert submissions.read_ids(p) == []
