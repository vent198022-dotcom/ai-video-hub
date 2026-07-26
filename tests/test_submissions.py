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
    videos, articles, repos = submissions.read_entries(p)
    assert videos == ["aaaaaaaaaaa", "bbbbbbbbbbb"]
    assert articles == [
        "https://www.inside.com.tw/article/12345",
        "https://medium.com/@someone/post-title",
    ]
    assert repos == []


def test_read_entries_dedups_articles(tmp_path):
    p = _write(tmp_path, "https://x.com/a\nhttps://x.com/a\nhttps://x.com/b\n")
    _, articles, _ = submissions.read_entries(p)
    assert articles == ["https://x.com/a", "https://x.com/b"]


def test_read_ids_still_returns_only_videos(tmp_path):
    p = _write(tmp_path, "https://youtu.be/bbbbbbbbbbb\nhttps://example.com/post\n")
    assert submissions.read_ids(p) == ["bbbbbbbbbbb"]


def test_read_entries_missing_file(tmp_path):
    assert submissions.read_entries(tmp_path / "nope.txt") == ([], [], [])


def test_parse_repo_accepts_common_forms():
    cases = [
        "https://github.com/langgenius/dify",
        "https://github.com/langgenius/dify/",
        "https://github.com/langgenius/dify.git",
        "https://github.com/langgenius/dify/tree/main",
        "https://github.com/langgenius/dify/blob/main/README.md",
        "https://github.com/langgenius/dify?tab=readme-ov-file",
        "https://github.com/langgenius/dify#installation",
        "http://github.com/langgenius/dify",
        "https://www.github.com/langgenius/dify",
    ]
    for u in cases:
        assert submissions.parse_repo(u) == "langgenius/dify", u


def test_parse_repo_rejects_non_repo_urls():
    for u in [
        "https://github.com/langgenius",
        "https://github.com/orgs/langgenius/repositories",
        "https://gist.github.com/someone/abc123",
        "https://gitlab.com/foo/bar",
        "https://example.com/foo/bar",
        "https://github.com/settings/profile",
        "https://github.com/topics/ai",
        "https://github.com/marketplace/actions/x",
        "not a url",
    ]:
        assert submissions.parse_repo(u) is None, u


def test_read_entries_splits_three_ways(tmp_path):
    p = _write(tmp_path, """
# 註解
https://www.youtube.com/watch?v=aaaaaaaaaaa
https://github.com/langgenius/dify
https://www.inside.com.tw/article/12345
https://github.com/langflow-ai/langflow/tree/main
https://youtu.be/bbbbbbbbbbb
""")
    videos, articles, repos = submissions.read_entries(p)
    assert videos == ["aaaaaaaaaaa", "bbbbbbbbbbb"]
    assert articles == ["https://www.inside.com.tw/article/12345"]
    assert repos == ["langgenius/dify", "langflow-ai/langflow"]


def test_read_entries_dedups_repos(tmp_path):
    p = _write(tmp_path,
               "https://github.com/a/b\nhttps://github.com/a/b/tree/main\n"
               "https://github.com/c/d\n")
    _, _, repos = submissions.read_entries(p)
    assert repos == ["a/b", "c/d"]


def test_read_entries_missing_file_three_empty(tmp_path):
    assert submissions.read_entries(tmp_path / "nope.txt") == ([], [], [])


def test_read_ids_still_only_videos(tmp_path):
    p = _write(tmp_path, "https://youtu.be/bbbbbbbbbbb\n"
                         "https://github.com/a/b\nhttps://example.com/post\n")
    assert submissions.read_ids(p) == ["bbbbbbbbbbb"]


def test_repo_url_containing_video_like_path_is_still_a_repo(tmp_path):
    """GitHub 網址中含 /embed/、/shorts/ 或 ?v= 時，不得被誤判為影片。"""
    p = _write(tmp_path, """
https://github.com/a/b/embed/abcdefghijk
https://github.com/c/d/tree/main/shorts/abcdefghijk
https://github.com/e/f?v=abcdefghijk12
""")
    videos, articles, repos = submissions.read_entries(p)
    assert videos == []
    assert articles == []
    assert repos == ["a/b", "c/d", "e/f"]


def test_youtube_urls_still_parse_as_videos(tmp_path):
    """反向確認：改順序後 YouTube 連結仍正確歸為影片。"""
    p = _write(tmp_path, """
https://www.youtube.com/watch?v=aaaaaaaaaaa
https://youtu.be/bbbbbbbbbbb
https://www.youtube.com/shorts/ccccccccccc
ddddddddddd
""")
    videos, articles, repos = submissions.read_entries(p)
    assert videos == ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc", "ddddddddddd"]
    assert repos == []
