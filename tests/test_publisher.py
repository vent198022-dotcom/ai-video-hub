"""publisher 模組測試。git 寫入操作以 mock 驗證，不真的 push。"""
import subprocess

import publisher


def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    return repo


def test_has_changes_detects_new_file(tmp_path):
    repo = _init_repo(tmp_path)
    assert publisher.has_changes(str(repo)) is False
    (repo / "新檔案.txt").write_text("內容", encoding="utf-8")
    assert publisher.has_changes(str(repo)) is True


def test_publish_skips_when_clean(monkeypatch):
    monkeypatch.setattr(publisher, "has_changes", lambda d: False)
    calls = []
    monkeypatch.setattr(publisher, "_git", lambda d, *a: calls.append(a))
    assert publisher.publish("repo") is False
    assert calls == []


def test_publish_adds_commits_pushes(monkeypatch):
    monkeypatch.setattr(publisher, "has_changes", lambda d: True)
    calls = []
    monkeypatch.setattr(publisher, "_git", lambda d, *a: calls.append(a))
    assert publisher.publish("repo") is True
    assert calls == [
        ("add", "-A"),
        ("commit", "-m", "chore: 更新影片資料"),
        ("push",),
    ]
