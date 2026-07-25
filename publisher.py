"""發佈模組：將整個 repo（含 docs/）commit 並 push 到 GitHub。"""
import logging
import subprocess

log = logging.getLogger(__name__)


def _git(repo_dir, *args):
    return subprocess.run(
        ["git", "-C", repo_dir, *args],
        capture_output=True, text=True, check=True, encoding="utf-8",
    )


def has_changes(repo_dir):
    result = _git(repo_dir, "status", "--porcelain")
    return bool(result.stdout.strip())


def publish(repo_dir, message="chore: 更新影片資料"):
    """有變更才 commit + push。回傳是否有發佈。"""
    if not has_changes(repo_dir):
        return False
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", message)
    _git(repo_dir, "push")
    return True
