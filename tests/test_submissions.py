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


def test_read_entries_splits_videos_and_articles(tmp_path):
    p = _write(tmp_path, """
# 註解
https://www.youtube.com/watch?v=aaaaaaaaaaa
https://www.inside.com.tw/article/12345
https://youtu.be/bbbbbbbbbbb
https://medium.com/@someone/post-title
隨手打的字
""")
    videos, articles = submissions.read_entries(p)
    assert videos == ["aaaaaaaaaaa", "bbbbbbbbbbb"]
    assert articles == [
        "https://www.inside.com.tw/article/12345",
        "https://medium.com/@someone/post-title",
    ]


def test_read_entries_dedups_articles(tmp_path):
    p = _write(tmp_path, "https://x.com/a\nhttps://x.com/a\nhttps://x.com/b\n")
    _, articles = submissions.read_entries(p)
    assert articles == ["https://x.com/a", "https://x.com/b"]


def test_read_ids_still_returns_only_videos(tmp_path):
    p = _write(tmp_path, "https://youtu.be/bbbbbbbbbbb\nhttps://example.com/post\n")
    assert submissions.read_ids(p) == ["bbbbbbbbbbb"]


def test_read_entries_missing_file(tmp_path):
    assert submissions.read_entries(tmp_path / "nope.txt") == ([], [])
