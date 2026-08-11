"""發佈模組：將整個 repo（含 docs/）commit 並 push 到 GitHub。"""
import logging
import subprocess

log = logging.getLogger(__name__)


def _git(repo_dir, *args, check=True):
    return subprocess.run(
        ["git", "-C", repo_dir, *args],
        capture_output=True, text=True, check=check, encoding="utf-8",
    )


def has_changes(repo_dir):
    result = _git(repo_dir, "status", "--porcelain")
    return bool(result.stdout.strip())


def _has_staged(repo_dir):
    """暫存區裡是否真的有內容變更。

    `git status --porcelain` 會回報假的「已修改」——索引快取的檔案大小過期時
    就會發生，例如 `.bat` 被重存成 CRLF，正規化後的 blob 其實和 HEAD 相同。
    那種情況 `git add -A` 什麼都不會 stage，接著 `git commit` 以退出碼 1 失敗，
    整個發佈階段就會拋例外。所以 add 之後要再確認一次真的有東西可 commit。

    `--quiet` 隱含 `--exit-code`：有變更回 1、沒變更回 0。尚無 HEAD 的空 repo
    會拿暫存區跟空樹相比，這個語意依然成立，不必特別處理。其他非 0 的退出碼
    （例如目標不是 git 工作目錄會回 129）視為有變更，交給 commit 自己去失敗，
    好讓真正的錯誤露出來，而不是被誤判成「沒東西要發佈」而靜默略過。
    """
    return _git(repo_dir, "diff", "--cached", "--quiet", check=False).returncode != 0


def publish(repo_dir, message="chore: 更新影片資料"):
    """有變更才 commit + push。回傳是否有發佈。"""
    if not has_changes(repo_dir):
        return False
    _git(repo_dir, "add", "-A")
    if not _has_staged(repo_dir):
        log.info("git add -A 後暫存區沒有實際內容變更，略過發佈"
                 "（常見於 .bat 換行正規化造成的假『已修改』）")
        return False
    _git(repo_dir, "commit", "-m", message)
    _git(repo_dir, "push")
    return True
