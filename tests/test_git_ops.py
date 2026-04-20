"""Unit tests for git operations."""

from unittest.mock import MagicMock, patch

from vcptoolbox_updater import git_ops
from vcptoolbox_updater.git_ops import GitOperator


def test_get_commit_hash():
    op = GitOperator("/tmp/repo", "origin", "main")
    with patch.object(git_ops, "_git_run") as mock_run:
        mock_run.return_value = MagicMock(stdout="abc1234\n")
        assert op.get_commit_hash("main") == "abc1234"
        mock_run.assert_called_once_with("/tmp/repo", ["rev-parse", "--short", "main"])


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
         patch.object(git_ops, "_git_run", return_value=MagicMock(returncode=0)) as mock_run:
        result = op.check_update_needed()
        assert not result.updated
        assert result.message == "Local is ahead of remote. No update needed."
        mock_run.assert_called_once_with(
            "/tmp/repo", ["merge-base", "is-ancestor", "origin/main", "main"], check=False
        )


def test_check_update_needed_local_behind():
    op = GitOperator("/tmp/repo", "origin", "main")

    def commit_hash_side_effect(ref):
        return "local1234" if ref == "main" else "remote5678"

    def run_side_effect(repo_path, cmd, **kwargs):
        if cmd == ["merge-base", "is-ancestor", "origin/main", "main"]:
            return MagicMock(returncode=1)
        if cmd == ["rev-list", "--count", "main..origin/main"]:
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
        return "local1234" if ref == "main" else "remote5678"

    def run_side_effect(repo_path, cmd, **kwargs):
        if cmd == ["merge-base", "is-ancestor", "origin/main", "main"]:
            return MagicMock(returncode=1)
        if cmd == ["rev-list", "--count", "main..origin/main"]:
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
        mock_run.assert_called_once_with("/tmp/repo", ["fetch", "origin"])


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
            return MagicMock(stdout="")
        return MagicMock(stdout="")

    with patch.object(op, "fetch") as mock_fetch, \
         patch.object(git_ops, "_git_run", side_effect=run_side_effect) as mock_run, \
         patch.object(op, "get_commit_hash", return_value="abc1234"):
        result = op.pull_and_resolve_conflicts()
        assert not result.updated
        mock_fetch.assert_called_once()
        mock_run.assert_any_call("/tmp/repo", ["status", "--porcelain"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["reset", "--hard", "abc1234"])


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
            return MagicMock(stdout="")
        if cmd == ["stash", "apply", "stash@{0}"]:
            return MagicMock(stdout="", returncode=0)
        if cmd == ["diff", "--name-only", "--diff-filter=MD", "def5678..stash@{0}"]:
            return MagicMock(stdout="file.txt\n")
        if cmd == ["checkout", "HEAD", "--", "file.txt"]:
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
        mock_run.assert_any_call("/tmp/repo", ["reset", "--hard", "def5678"])
        mock_run.assert_any_call("/tmp/repo", ["stash", "apply", "stash@{0}"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["diff", "--name-only", "--diff-filter=MD", "def5678..stash@{0}"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["checkout", "HEAD", "--", "file.txt"])
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
        # No stash created because no tracked changes
        calls = [c.args for c in mock_run.call_args_list]
        assert ("/tmp/repo", ["stash", "push", "-m", "local"]) not in calls
        mock_run.assert_any_call("/tmp/repo", ["reset", "--hard", "def5678"])


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
            return MagicMock(stdout="")
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
        mock_run.assert_any_call("/tmp/repo", ["reset", "--hard", "def5678"])
        mock_run.assert_any_call("/tmp/repo", ["stash", "apply", "stash@{0}"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["diff", "--name-only", "--diff-filter=MD", "def5678..stash@{0}"], check=False)
        mock_run.assert_any_call("/tmp/repo", ["stash", "drop", "stash@{0}"])
        # Must NOT checkout HEAD for new_feature.py
        calls = [c.args for c in mock_run.call_args_list]
        assert ("/tmp/repo", ["checkout", "HEAD", "--", "new_feature.py"]) not in calls


def test_pull_and_resolve_conflicts_detached_head():
    """Detached HEAD should be detected and checked out before syncing."""
    op = GitOperator("/tmp/repo", "origin", "main")

    def run_side_effect(repo_path, cmd, **kwargs):
        if cmd == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return MagicMock(stdout="HEAD")
        if cmd == ["checkout", "main"]:
            return MagicMock(stdout="")
        if cmd == ["status", "--porcelain"]:
            return MagicMock(stdout="")
        if cmd == ["rev-parse", "--short", "origin/main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["rev-parse", "--short", "HEAD"]:
            return MagicMock(stdout="abc1234")
        if cmd == ["rev-parse", "--short", "main"]:
            return MagicMock(stdout="def5678")
        if cmd == ["add", "-u"]:
            return MagicMock(stdout="")
        if cmd == ["reset", "--hard", "def5678"]:
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
        mock_run.assert_any_call("/tmp/repo", ["checkout", "main"])
        mock_run.assert_any_call("/tmp/repo", ["reset", "--hard", "def5678"])
