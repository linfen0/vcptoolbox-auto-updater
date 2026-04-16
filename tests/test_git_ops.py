"""Unit tests for git operations."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from vcptoolbox_updater.git_ops import GitOperator


def test_get_commit_hash():
    op = GitOperator("/tmp/repo", "origin", "main")
    with patch.object(op, "_run") as mock_run:
        mock_run.return_value = MagicMock(stdout="abc1234\n")
        assert op.get_commit_hash("main") == "abc1234"
        mock_run.assert_called_once_with(["rev-parse", "--short", "main"])


def test_check_update_needed_no_update_same_commit():
    op = GitOperator("/tmp/repo", "origin", "main")
    with patch.object(op, "get_commit_hash", return_value="abc1234"):
        result = op.check_update_needed()
        assert not result.updated
        assert result.message == "Already up to date."


def test_check_update_needed_local_ahead():
    op = GitOperator("/tmp/repo", "origin", "main")

    def commit_hash_side_effect(ref):
        return "local5678" if ref == "main" else "remote1234"

    with patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect), \
         patch.object(op, "_run", return_value=MagicMock(returncode=0)) as mock_run:
        result = op.check_update_needed()
        assert not result.updated
        assert result.message == "Local is ahead of remote. No update needed."
        mock_run.assert_called_once_with(
            ["merge-base", "--is-ancestor", "origin/main", "main"], check=False
        )


def test_check_update_needed_local_behind():
    op = GitOperator("/tmp/repo", "origin", "main")

    def commit_hash_side_effect(ref):
        return "local1234" if ref == "main" else "remote5678"

    def run_side_effect(cmd, **kwargs):
        if cmd == ["merge-base", "--is-ancestor", "origin/main", "main"]:
            return MagicMock(returncode=1)
        if cmd == ["rev-list", "--count", "main..origin/main"]:
            return MagicMock(stdout="3")
        return MagicMock()

    with patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect), \
         patch.object(op, "_run", side_effect=run_side_effect):
        result = op.check_update_needed()
        assert result.updated
        assert "Behind by 3 commit(s)" in result.message


def test_check_update_needed_diverged():
    op = GitOperator("/tmp/repo", "origin", "main")

    def commit_hash_side_effect(ref):
        return "local1234" if ref == "main" else "remote5678"

    def run_side_effect(cmd, **kwargs):
        if cmd == ["merge-base", "--is-ancestor", "origin/main", "main"]:
            return MagicMock(returncode=1)
        if cmd == ["rev-list", "--count", "main..origin/main"]:
            return MagicMock(stdout="2")
        return MagicMock()

    with patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect), \
         patch.object(op, "_run", side_effect=run_side_effect):
        result = op.check_update_needed()
        assert result.updated
        assert "Behind by 2 commit(s)" in result.message


def test_fetch():
    op = GitOperator("/tmp/repo", "origin", "main")
    with patch.object(op, "_run", return_value=MagicMock(stdout="fetch output")) as mock_run:
        op.fetch()
        mock_run.assert_called_once_with(["fetch", "origin"])


def test_pull_and_resolve_conflicts_no_update():
    op = GitOperator("/tmp/repo", "origin", "main")
    mock_result = MagicMock()
    mock_result.updated = False
    mock_result.local_commit = "abc1234"
    mock_result.remote_commit = "abc1234"
    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(op, "check_update_needed", return_value=mock_result), \
         patch.object(op, "get_commit_hash", return_value="abc1234"):
        result = op.pull_and_resolve_conflicts()
        assert not result.updated
        mock_fetch.assert_called_once()


def test_pull_and_resolve_conflicts_with_update_no_local_changes():
    op = GitOperator("/tmp/repo", "origin", "main")
    mock_result = MagicMock()
    mock_result.updated = True
    mock_result.local_commit = "abc1234"
    mock_result.remote_commit = "def5678"

    commit_calls = iter(["abc1234", "def5678"])

    def commit_hash_side_effect(ref):
        return next(commit_calls)

    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(op, "check_update_needed", return_value=mock_result), \
         patch.object(op, "_run", return_value=MagicMock(stdout="", returncode=0)) as mock_run, \
         patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect):
        result = op.pull_and_resolve_conflicts()
        assert result.updated
        assert result.local_commit == "abc1234"
        assert result.remote_commit == "def5678"
        mock_fetch.assert_called_once()
        mock_run.assert_any_call(["status", "--porcelain"], check=False)
        mock_run.assert_any_call(["merge", "-X", "theirs", "origin/main"], check=False)


def test_pull_and_resolve_conflicts_with_tracked_local_changes():
    op = GitOperator("/tmp/repo", "origin", "main")
    mock_result = MagicMock()
    mock_result.updated = True
    mock_result.local_commit = "abc1234"
    mock_result.remote_commit = "def5678"

    def run_side_effect(cmd, **kwargs):
        if cmd == ["status", "--porcelain"]:
            return MagicMock(stdout=" M file.txt\n?? untracked.log")
        if cmd == ["merge", "-X", "theirs", "origin/main"]:
            return MagicMock(stdout="", returncode=0)
        return MagicMock(stdout="")

    def commit_hash_side_effect(ref):
        if ref == "main":
            return "def5678"
        return "abc1234"

    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(op, "check_update_needed", return_value=mock_result), \
         patch.object(op, "_run", side_effect=run_side_effect) as mock_run, \
         patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect):
        result = op.pull_and_resolve_conflicts()
        assert result.updated
        mock_run.assert_any_call(["status", "--porcelain"], check=False)
        mock_run.assert_any_call(["add", "-u"])
        mock_run.assert_any_call(["commit", "-m", "auto-updater: preserve local changes"])
        mock_run.assert_any_call(["merge", "-X", "theirs", "origin/main"], check=False)


def test_pull_and_resolve_conflicts_merge_conflict_prefer_remote():
    op = GitOperator("/tmp/repo", "origin", "main")
    mock_result = MagicMock()
    mock_result.updated = True
    mock_result.local_commit = "abc1234"
    mock_result.remote_commit = "def5678"

    def run_side_effect(cmd, **kwargs):
        if cmd == ["status", "--porcelain"]:
            return MagicMock(stdout="")
        if cmd == ["merge", "-X", "theirs", "origin/main"]:
            return MagicMock(stdout="", returncode=1)
        return MagicMock(stdout="")

    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(op, "check_update_needed", return_value=mock_result), \
         patch.object(op, "_run", side_effect=run_side_effect) as mock_run, \
         patch.object(op, "get_commit_hash", return_value="def5678"):
        result = op.pull_and_resolve_conflicts()
        assert result.updated
        mock_run.assert_any_call(["merge", "-X", "theirs", "origin/main"], check=False)
        mock_run.assert_any_call(["checkout", "--theirs", "."])
        mock_run.assert_any_call(["add", "-u"])
        mock_run.assert_any_call(["commit", "-m", "Merge origin/main (prefer remote changes)"])


def test_pull_and_resolve_conflicts_preserves_untracked_files():
    op = GitOperator("/tmp/repo", "origin", "main")
    mock_result = MagicMock()
    mock_result.updated = True
    mock_result.local_commit = "abc1234"
    mock_result.remote_commit = "def5678"

    def run_side_effect(cmd, **kwargs):
        if cmd == ["status", "--porcelain"]:
            return MagicMock(stdout="?? untracked.log\n?? temp/data.json")
        if cmd == ["merge", "-X", "theirs", "origin/main"]:
            return MagicMock(stdout="", returncode=0)
        return MagicMock(stdout="")

    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(op, "check_update_needed", return_value=mock_result), \
         patch.object(op, "_run", side_effect=run_side_effect) as mock_run, \
         patch.object(op, "get_commit_hash", return_value="def5678"):
        result = op.pull_and_resolve_conflicts()
        assert result.updated
        # 没有 tracked changes，所以不应该执行 add -u / commit
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["add", "-u"] not in calls
        assert ["commit", "-m", "auto-updater: preserve local changes"] not in calls
        mock_run.assert_any_call(["merge", "-X", "theirs", "origin/main"], check=False)
