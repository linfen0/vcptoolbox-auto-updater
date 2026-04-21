"""Unit tests for git operations."""

import os
from unittest.mock import MagicMock, patch

from vcptoolbox_updater import git_ops
from vcptoolbox_updater.git_ops import GitOperator


def test_get_commit_hash():
    op = GitOperator("/tmp/repo", "origin", "main")
    with patch.object(git_ops, "_git_run") as mock_run:
        mock_run.return_value = MagicMock(stdout="abc1234\n")
        assert op.get_commit_hash("main") == "abc1234"
        mock_run.assert_called_once_with("/tmp/repo", ["rev-parse", "--short", "main"])


def test_is_detached_head_true():
    op = GitOperator("/tmp/repo", "origin", "main")
    with patch.object(git_ops, "_git_run") as mock_run:
        mock_run.return_value = MagicMock(stdout="HEAD\n")
        assert op.is_detached_head() is True
        mock_run.assert_called_once_with("/tmp/repo", ["rev-parse", "--abbrev-ref", "HEAD"])


def test_is_detached_head_false():
    op = GitOperator("/tmp/repo", "origin", "main")
    with patch.object(git_ops, "_git_run") as mock_run:
        mock_run.return_value = MagicMock(stdout="main\n")
        assert op.is_detached_head() is False
        mock_run.assert_called_once_with("/tmp/repo", ["rev-parse", "--abbrev-ref", "HEAD"])


def test_check_update_needed_no_update_same_commit():
    op = GitOperator("/tmp/repo", "origin", "main")
    with patch.object(op, "get_commit_hash", return_value="abc1234"):
        result = op.check_update_needed()
        assert not result.updated
        assert result.message == "Already up to date."


def test_check_update_needed_local_ahead():
    op = GitOperator("/tmp/repo", "origin", "main")

    def commit_hash_side_effect(ref):
        if ref == "HEAD":
            return "local5678"
        if ref == "origin/main":
            return "remote1234"
        return "abc1234"

    with patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect), \
         patch.object(git_ops, "_git_run", return_value=MagicMock(returncode=0)) as mock_run:
        result = op.check_update_needed()
        assert not result.updated
        assert result.message == "Local is ahead of remote. No update needed."
        mock_run.assert_called_once_with(
            "/tmp/repo", ["merge-base", "is-ancestor", "origin/main", "HEAD"], check=False
        )


def test_check_update_needed_local_behind():
    op = GitOperator("/tmp/repo", "origin", "main")

    def commit_hash_side_effect(ref):
        if ref == "HEAD":
            return "local1234"
        if ref == "origin/main":
            return "remote5678"
        return "abc1234"

    def run_side_effect(repo_path, cmd, **kwargs):
        if cmd == ["merge-base", "is-ancestor", "origin/main", "HEAD"]:
            return MagicMock(returncode=1)
        if cmd == ["rev-list", "--count", "HEAD..origin/main"]:
            return MagicMock(stdout="3")
        return MagicMock()

    with patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect), \
         patch.object(git_ops, "_git_run", side_effect=run_side_effect):
        result = op.check_update_needed()
        assert result.updated
        assert "Behind by 3 commit(s)" in result.message


def test_check_update_needed_diverged():
    op = GitOperator("/tmp/repo", "origin", "main")

    def commit_hash_side_effect(ref):
        if ref == "HEAD":
            return "local1234"
        if ref == "origin/main":
            return "remote5678"
        return "abc1234"

    def run_side_effect(repo_path, cmd, **kwargs):
        if cmd == ["merge-base", "is-ancestor", "origin/main", "HEAD"]:
            return MagicMock(returncode=1)
        if cmd == ["rev-list", "--count", "HEAD..origin/main"]:
            return MagicMock(stdout="2")
        return MagicMock()

    with patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect), \
         patch.object(git_ops, "_git_run", side_effect=run_side_effect):
        result = op.check_update_needed()
        assert result.updated
        assert "Behind by 2 commit(s)" in result.message


def test_fetch():
    op = GitOperator("/tmp/repo", "origin", "main")
    with patch.object(git_ops, "_git_run", return_value=MagicMock(stdout="fetch output")) as mock_run:
        op.fetch()
        mock_run.assert_any_call("/tmp/repo", ["fetch", "origin"])


def test_pull_and_resolve_conflicts_no_update():
    """Local and remote are identical: no stash, no reset effect."""
    op = GitOperator("/tmp/repo", "origin", "main")

    def run_side_effect(repo_path, cmd, **kwargs):
        if cmd == ["status", "--porcelain"]:
            return MagicMock(stdout="")
        if cmd == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return MagicMock(stdout="main")
        if cmd == ["rev-parse", "--short", "origin/main"]:
            return MagicMock(stdout="abc1234")
        if cmd == ["rev-parse", "--short", "HEAD"]:
            return MagicMock(stdout="abc1234")
        if cmd == ["rev-parse", "--short", "main"]:
            return MagicMock(stdout="abc1234")
        if cmd == ["add", "-u"]:
            return MagicMock(stdout="")
        if cmd == ["reset", "--hard", "abc1234"]:
            return MagicMock(stdout="", returncode=0)
        return MagicMock(stdout="")

    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(git_ops, "_git_run", side_effect=run_side_effect) as mock_run, \
         patch.object(op, "get_commit_hash", return_value="abc1234"):
        result = op.pull_and_resolve_conflicts()
        assert not result.updated
        mock_fetch.assert_called_once()
        mock_run.assert_any_call("/tmp/repo", ["status", "--porcelain"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["reset", "--hard", "abc1234"], check=False)


def test_pull_and_resolve_conflicts_with_tracked_local_changes():
    """Tracked local changes are stashed, reset to remote, then reconciled."""
    op = GitOperator("/tmp/repo", "origin", "main")

    def run_side_effect(repo_path, cmd, **kwargs):
        if cmd == ["status", "--porcelain"]:
            return MagicMock(stdout=" M file.txt\n?? untracked.log")
        if cmd == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return MagicMock(stdout="main")
        if cmd == ["rev-parse", "--short", "origin/main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["rev-parse", "--short", "HEAD"]:
            return MagicMock(stdout="abc1234")
        if cmd == ["rev-parse", "--short", "main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["add", "-u"]:
            return MagicMock(stdout="")
        if cmd == ["stash", "push", "-m", "local"]:
            return MagicMock(stdout="")
        if cmd == ["reset", "--hard", "def5678"]:
            return MagicMock(stdout="", returncode=0)
        if cmd == ["stash", "apply", "stash@{0}"]:
            return MagicMock(stdout="", returncode=0)
        if cmd == ["diff", "--name-only", "--diff-filter=MD", "def5678..stash@{0}"]:
            return MagicMock(stdout="file.txt\n")
        if cmd == ["diff", "--name-only", "--diff-filter=U"]:
            return MagicMock(stdout="")
        if cmd == ["ls-tree", "-r", "HEAD", "--name-only"]:
            return MagicMock(stdout="file.txt\n")
        if cmd == ["checkout", "HEAD", "--pathspec-from-file=-"]:
            return MagicMock(stdout="")
        if cmd == ["stash", "drop", "stash@{0}"]:
            return MagicMock(stdout="")
        return MagicMock(stdout="")

    def commit_hash_side_effect(ref):
        if ref == "HEAD":
            return "abc1234"
        return "def5678"

    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(git_ops, "_git_run", side_effect=run_side_effect) as mock_run, \
         patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect):
        result = op.pull_and_resolve_conflicts()
        assert result.updated
        assert result.local_commit == "abc1234"
        assert result.remote_commit == "def5678"
        mock_fetch.assert_called_once()
        mock_run.assert_any_call("/tmp/repo", ["add", "-u"])
        mock_run.assert_any_call("/tmp/repo", ["stash", "push", "-m", "local"])
        mock_run.assert_any_call("/tmp/repo", ["reset", "--hard", "def5678"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["stash", "apply", "stash@{0}"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["diff", "--name-only", "--diff-filter=MD", "def5678..stash@{0}"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["diff", "--name-only", "--diff-filter=U"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["ls-tree", "-r", "HEAD", "--name-only"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["checkout", "HEAD", "--pathspec-from-file=-"], input="file.txt")
        mock_run.assert_any_call("/tmp/repo", ["stash", "drop", "stash@{0}"])


def test_pull_and_resolve_conflicts_preserves_untracked_files():
    """Untracked files should be left untouched throughout the sync."""
    op = GitOperator("/tmp/repo", "origin", "main")

    def run_side_effect(repo_path, cmd, **kwargs):
        if cmd == ["status", "--porcelain"]:
            return MagicMock(stdout="?? untracked.log\n?? temp/data.json")
        if cmd == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return MagicMock(stdout="main")
        if cmd == ["rev-parse", "--short", "origin/main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["rev-parse", "--short", "HEAD"]:
            return MagicMock(stdout="abc1234")
        if cmd == ["rev-parse", "--short", "main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["add", "-u"]:
            return MagicMock(stdout="")
        if cmd == ["reset", "--hard", "def5678"]:
            return MagicMock(stdout="", returncode=0)
        return MagicMock(stdout="")

    def commit_hash_side_effect(ref):
        if ref == "HEAD":
            return "abc1234"
        return "def5678"

    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(git_ops, "_git_run", side_effect=run_side_effect) as mock_run, \
         patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect):
        result = op.pull_and_resolve_conflicts()
        assert result.updated
        # No stash created because no tracked changes
        calls = [c.args for c in mock_run.call_args_list]
        assert ("/tmp/repo", ["stash", "push", "-m", "local"]) not in calls
        mock_run.assert_any_call("/tmp/repo", ["reset", "--hard", "def5678"], check=False)


def test_pull_and_resolve_conflicts_new_local_files_kept():
    """Files added locally (A in stash) should be preserved, not reverted."""
    op = GitOperator("/tmp/repo", "origin", "main")

    def run_side_effect(repo_path, cmd, **kwargs):
        if cmd == ["status", "--porcelain"]:
            return MagicMock(stdout="A  new_feature.py")
        if cmd == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return MagicMock(stdout="main")
        if cmd == ["rev-parse", "--short", "origin/main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["rev-parse", "--short", "HEAD"]:
            return MagicMock(stdout="abc1234")
        if cmd == ["rev-parse", "--short", "main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["add", "-u"]:
            return MagicMock(stdout="")
        if cmd == ["stash", "push", "-m", "local"]:
            return MagicMock(stdout="")
        if cmd == ["reset", "--hard", "def5678"]:
            return MagicMock(stdout="", returncode=0)
        if cmd == ["stash", "apply", "stash@{0}"]:
            return MagicMock(stdout="", returncode=0)
        # diff-filter=MD returns nothing because new_feature.py is Added, not Modified/Deleted
        if cmd == ["diff", "--name-only", "--diff-filter=MD", "def5678..stash@{0}"]:
            return MagicMock(stdout="")
        if cmd == ["stash", "drop", "stash@{0}"]:
            return MagicMock(stdout="")
        return MagicMock(stdout="")

    def commit_hash_side_effect(ref):
        if ref == "HEAD":
            return "abc1234"
        return "def5678"

    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(git_ops, "_git_run", side_effect=run_side_effect) as mock_run, \
         patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect):
        result = op.pull_and_resolve_conflicts()
        assert result.updated
        mock_run.assert_any_call("/tmp/repo", ["stash", "push", "-m", "local"])
        mock_run.assert_any_call("/tmp/repo", ["reset", "--hard", "def5678"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["stash", "apply", "stash@{0}"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["diff", "--name-only", "--diff-filter=MD", "def5678..stash@{0}"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["stash", "drop", "stash@{0}"])
        # Must NOT checkout HEAD for new_feature.py
        calls = [c.args for c in mock_run.call_args_list]
        assert ("/tmp/repo", ["checkout", "HEAD", "--pathspec-from-file=-"], {"input": "new_feature.py", "check": False}) not in calls


def test_pull_and_resolve_conflicts_detached_head():
    """Detached HEAD with local changes: stash first, then checkout, then sync."""
    op = GitOperator("/tmp/repo", "origin", "main")

    def run_side_effect(repo_path, cmd, **kwargs):
        if cmd == ["checkout", "main"]:
            return MagicMock(stdout="")
        if cmd == ["status", "--porcelain"]:
            return MagicMock(stdout=" M file.txt\n")
        if cmd == ["add", "-u"]:
            return MagicMock(stdout="")
        if cmd == ["stash", "push", "-m", "local"]:
            return MagicMock(stdout="")
        if cmd == ["stash", "apply", "stash@{0}"]:
            return MagicMock(stdout="", returncode=0)
        if cmd == ["diff", "--name-only", "--diff-filter=MD", "def5678..stash@{0}"]:
            return MagicMock(stdout="file.txt\n")
        if cmd == ["diff", "--name-only", "--diff-filter=U"]:
            return MagicMock(stdout="")
        if cmd == ["ls-tree", "-r", "HEAD", "--name-only"]:
            return MagicMock(stdout="file.txt\n")
        if cmd == ["checkout", "HEAD", "--pathspec-from-file=-"]:
            return MagicMock(stdout="")
        if cmd == ["stash", "drop", "stash@{0}"]:
            return MagicMock(stdout="")
        if cmd == ["rev-parse", "--short", "origin/main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["rev-parse", "--short", "HEAD"]:
            return MagicMock(stdout="abc1234")
        if cmd == ["rev-parse", "--short", "main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["reset", "--hard", "def5678"]:
            return MagicMock(stdout="", returncode=0)
        return MagicMock(stdout="")

    def commit_hash_side_effect(ref):
        if ref == "HEAD":
            return "abc1234"
        return "def5678"

    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(op, "is_detached_head", return_value=True), \
         patch.object(git_ops, "_git_run", side_effect=run_side_effect) as mock_run, \
         patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect):
        result = op.pull_and_resolve_conflicts()
        assert result.updated
        calls = [c.args for c in mock_run.call_args_list]
        stash_idx = calls.index(("/tmp/repo", ["stash", "push", "-m", "local"]))
        checkout_idx = calls.index(("/tmp/repo", ["checkout", "main"]))
        assert stash_idx < checkout_idx, "stash must happen before checkout in detached HEAD"
        mock_run.assert_any_call("/tmp/repo", ["checkout", "main"])
        mock_run.assert_any_call("/tmp/repo", ["reset", "--hard", "def5678"], check=False)


def test_pull_and_resolve_conflicts_untracked_conflicts_with_remote_new_file():
    """Untracked files that collide with newly-tracked remote files are removed on retry."""
    op = GitOperator("/tmp/repo", "origin", "main")

    reset_call_count = 0

    def run_side_effect(repo_path, cmd, **kwargs):
        nonlocal reset_call_count
        if cmd == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return MagicMock(stdout="main")
        if cmd == ["rev-parse", "--short", "origin/main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["rev-parse", "--short", "HEAD"]:
            return MagicMock(stdout="abc1234")
        if cmd == ["rev-parse", "--short", "main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["status", "--porcelain"]:
            return MagicMock(stdout="")
        if cmd == ["add", "-u"]:
            return MagicMock(stdout="")
        if cmd == ["reset", "--hard", "def5678"]:
            reset_call_count += 1
            if reset_call_count == 1:
                return MagicMock(
                    returncode=1,
                    stderr=(
                        "error: The following untracked working tree files would be overwritten by checkout:\n"
                        "\tconfig.env\n"
                        "Please move or remove them before you switch branches.\n"
                        "Aborting\n"
                    ),
                )
            return MagicMock(stdout="")
        return MagicMock(stdout="")

    def commit_hash_side_effect(ref):
        if ref == "HEAD":
            return "abc1234"
        return "def5678"

    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(git_ops, "_git_run", side_effect=run_side_effect) as mock_run, \
         patch.object(op, "get_commit_hash", side_effect=commit_hash_side_effect), \
         patch("vcptoolbox_updater.git_ops.os.remove") as mock_remove, \
         patch("vcptoolbox_updater.git_ops.os.path.isdir", return_value=False):
        result = op.pull_and_resolve_conflicts()
        assert result.updated
        # reset --hard should have been called twice (fail then retry)
        assert reset_call_count == 2
        mock_remove.assert_called_once_with(os.path.join("/tmp/repo", "config.env"))
        mock_run.assert_any_call("/tmp/repo", ["reset", "--hard", "def5678"], check=False)
