"""publisher 模組測試。git 寫入操作以 mock 驗證，不真的 push。"""
import subprocess
from types import SimpleNamespace

import publisher


def _stub(calls, returncode):
    """記錄呼叫序列的 _git 替身。

    刻意回傳帶 returncode 的物件，而不是 None——這樣 `_has_staged()` 的退出碼
    判斷邏輯會被真的執行到。若替身回 None 就只能連 `_has_staged` 一起 patch 掉，
    那條映射邏輯便沒有任何測試走過：實測「`_has_staged` 永遠回 False」
    這個會讓網站從此不再發佈的突變，在那種寫法下全套測試依然全綠。
    """
    def fake(repo_dir, *args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=returncode, stdout="", stderr="")
    return fake


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


def test_publish_survives_fake_modified(tmp_path):
    """索引 stat 快取過期造成的假「已修改」不能讓發佈階段爆掉。

    `.bat` 被重存成 CRLF 後，正規化的 blob 與 HEAD 相同，但檔案大小變了，
    於是 `git status --porcelain` 報 M、`git add -A` 卻什麼都沒 stage。
    照常 commit 會拿到退出碼 1，check=True 便拋 CalledProcessError。
    """
    repo = _init_repo(tmp_path)
    # 這兩行請勿刪：全域 git 沒有設 user.email／user.name（只設在本 repo 的
    # .git/config 裡），乾淨機器上少了它們這個測試根本跑不起來。而且沒有它們時，
    # 修正被移除的失敗理由會變成「不知道作者是誰」(退出碼 128) 而不是真正的
    # 「沒東西可 commit」(退出碼 1)——測試會因為錯誤的理由變紅。
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(repo), "config", k, v],
                       check=True, capture_output=True)
    (repo / ".gitattributes").write_text("*.bat text eol=crlf\n", encoding="utf-8")
    (repo / "run.bat").write_bytes("@echo off\nrem AI 測試\n".encode("utf-8"))
    subprocess.run(["git", "-C", str(repo), "add", "-A"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"],
                   check=True, capture_output=True)

    # 只改換行，內容不變
    (repo / "run.bat").write_bytes("@echo off\r\nrem AI 測試\r\n".encode("utf-8"))

    assert publisher.has_changes(str(repo)) is True   # status 看得到假的 M
    assert publisher.publish(str(repo)) is False      # 但不該 commit，也不該拋例外


def test_publish_adds_commits_pushes(monkeypatch):
    monkeypatch.setattr(publisher, "has_changes", lambda d: True)
    calls = []
    monkeypatch.setattr(publisher, "_git", _stub(calls, 1))   # 1 = 有 staged 變更
    assert publisher.publish("repo") is True
    assert calls == [
        ("add", "-A"),
        ("diff", "--cached", "--quiet"),
        ("commit", "-m", "chore: 更新影片資料"),
        ("push",),
    ]


def test_publish_stops_after_add_when_nothing_staged(monkeypatch):
    """假變更時只能跑到 add 與檢查，不得往下 commit／push。"""
    monkeypatch.setattr(publisher, "has_changes", lambda d: True)
    calls = []
    monkeypatch.setattr(publisher, "_git", _stub(calls, 0))   # 0 = 暫存區乾淨
    assert publisher.publish("repo") is False
    assert calls == [("add", "-A"), ("diff", "--cached", "--quiet")]
