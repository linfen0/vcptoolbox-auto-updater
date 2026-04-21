"""Git operations: fetch and sync to remote, preserving only new files from local stash.

The core sync strategy (``pull_and_resolve_conflicts``) works as follows:

1. Stash any local tracked changes (``git stash push -m "local"``).
2. Hard-reset to the remote commit (``git reset --hard <remote_hash>``).
   If untracked files block the reset, parse the error, remove only those
   conflicting files, and retry the reset.
3. Apply the stash back (``git stash apply``). Conflicts are ignored because
   we reconcile manually in the next step.
4. For every file that was **modified** or **deleted** in the stash,
   force the remote (HEAD) version (``git checkout HEAD -- <file>``).
5. Files that were **added** in the stash remain as-is.
6. Drop the stash.

Result: the working tree contains the exact remote state plus any *new*
local files that did not exist on the remote.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

from vcptoolbox_updater.utils import get_logger

logger = get_logger(__name__)


def _parse_untracked_reset_conflicts(stderr: str) -> list[str]:
    """Extract untracked file paths from a failed ``git reset --hard`` stderr.

    Git emits output like::

        error: The following untracked working tree files would be overwritten by checkout:
            config.env
            another.file
        Please move or remove them before you switch branches.
        Aborting

    This function collects the indented file names and returns them as a list.
    If the stderr does not match the expected pattern, an empty list is
    returned so that the caller can treat it as a non-conflict error.

    Args:
        stderr: Raw stderr text from the failed git command.

    Returns:
        List of relative file paths that caused the reset to abort.
    """
    lines = stderr.splitlines()
    files: list[str] = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if "would be overwritten by checkout:" in stripped:
            in_block = True
            continue
        if in_block:
            if not stripped:
                break
            # Git indents file names with a leading tab or spaces.
            # We only take lines that look like indented file paths.
            if line.startswith("\t") or line.startswith(" "):
                files.append(stripped)
            else:
                break
    return files


@dataclass(frozen=True, slots=True)
class GitUpdateResult:
    """Outcome of a single update attempt.

    Attributes:
        updated: ``True`` if the local branch moved to a different commit.
        local_commit: Short hash of the local commit before the operation.
        remote_commit: Short hash of the local commit after the operation.
        message: Human-readable description of what happened.
    """

    updated: bool
    local_commit: str
    remote_commit: str
    message: str


def _git_run(repo_path: str, cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Execute a git sub-process and return its result.

    Args:
        repo_path: Path to the git repository (used as *cwd*).
        cmd: Git sub-command arguments (e.g. ``["fetch", "origin"]``).
        check: When ``True`` (default), raise ``RuntimeError`` on non-zero exit.

    Returns:
        The completed process object.

    Raises:
        RuntimeError: If *check* is ``True`` and the command exits with a non-zero code.
    """
    full_cmd = ["git", *cmd]
    logger.debug("running_git_command", command=" ".join(full_cmd), cwd=repo_path)
    result = subprocess.run(
        full_cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if check and result.returncode != 0:
        err_msg = result.stderr.strip() or "(no stderr output)"
        raise RuntimeError(
            f"Git command failed in {repo_path}: "
            f"{' '.join(full_cmd)}\n"
            f"Error: {err_msg}"
        )
    return result


class GitOperator:
    """Encapsulates all git interactions for a single repository/branch pair."""

    def __init__(self, repo_path: str, remote_name: str, branch: str) -> None:
        """Initialise the operator.

        Args:
            repo_path: Absolute path to the local git repository.
            remote_name: Name of the remote (e.g. ``"origin"``).
            branch: Branch to track (e.g. ``"main"``).
        """
        self.repo_path = repo_path
        self.remote_name = remote_name
        self.branch = branch
        self.remote_ref = f"{remote_name}/{branch}"

    def fetch(self) -> None:
        """Run ``git fetch <remote_name>`` for the configured remote."""
        result = _git_run(self.repo_path, ["fetch", self.remote_name])
        logger.info("git_fetch_completed", stdout=result.stdout.strip())

    def get_commit_hash(self, ref: str) -> str:
        """Return the short SHA-1 of *ref*.

        Args:
            ref: Any git rev-parse accepted reference (branch, tag, HEAD, …).

        Returns:
            The 7-character short hash as a string.
        """
        result = _git_run(self.repo_path, ["rev-parse", "--short", ref])
        return result.stdout.strip()

    def check_update_needed(self) -> GitUpdateResult:
        """Determine whether the local branch is behind the remote.

        The method also handles the "local is ahead" case (no update required).

        Returns:
            A :class:`GitUpdateResult` describing the comparison outcome.
        """
        local_commit = self.get_commit_hash(self.branch)
        remote_commit = self.get_commit_hash(self.remote_ref)

        if local_commit == remote_commit:
            return GitUpdateResult(
                updated=False,
                local_commit=local_commit,
                remote_commit=remote_commit,
                message="Already up to date.",
            )

        ancestor_result = _git_run(
            self.repo_path,
            ["merge-base", "is-ancestor", self.remote_ref, self.branch],
            check=False,
        )
        if ancestor_result.returncode == 0:
            return GitUpdateResult(
                updated=False,
                local_commit=local_commit,
                remote_commit=remote_commit,
                message="Local is ahead of remote. No update needed.",
            )

        try:
            count_result = _git_run(
                self.repo_path,
                ["rev-list", "--count", f"{self.branch}..{self.remote_ref}"],
            )
            behind_count = int(count_result.stdout.strip())
        except Exception:
            behind_count = -1

        return GitUpdateResult(
            updated=True,
            local_commit=local_commit,
            remote_commit=remote_commit,
            message=f"Behind by {behind_count} commit(s).",
        )

    def pull_and_resolve_conflicts(self) -> GitUpdateResult:
        """Synchronise the local branch to the remote state.

        This is the main entry-point used by the scheduler / CLI.  It always
        performs a fetch, stashes local tracked changes, hard-resets to the
        remote commit, then applies the stash back while discarding any
        modifications or deletions that conflict with the remote version.
        Only *new* files (added locally) survive the operation.

        If ``git reset --hard`` aborts because of untracked file collisions,
        the conflicting files are removed and the reset is retried **once**.
        This avoids the overhead of scanning all untracked files on every run.

        Returns:
            A :class:`GitUpdateResult` indicating whether the working tree
            actually changed commits.
        """
        pre_local = self.get_commit_hash("HEAD")
        self.fetch()

        remote_hash = self.get_commit_hash(self.remote_ref)

        # 1. Stash local tracked changes if any (before checkout to preserve detached-HEAD changes)
        _git_run(self.repo_path, ["add", "-u"])
        status_result = _git_run(self.repo_path, ["status", "--porcelain"], check=False)
        has_tracked = any(
            line and not line.startswith("?")
            for line in status_result.stdout.strip().splitlines()
        )
        local_stash = None
        if has_tracked:
            _git_run(self.repo_path, ["stash", "push", "-m", "local"])
            local_stash = "stash@{0}"
            logger.info("local_tracked_changes_stashed", stash=local_stash)

        # 2. Detached HEAD -> checkout branch first
        head_ref = _git_run(self.repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
        if head_ref.stdout.strip() == "HEAD":
            logger.warning("detached_head_checking_out", branch=self.branch)
            _git_run(self.repo_path, ["checkout", self.branch])
            logger.info("checked_out_branch", branch=self.branch)

        # 3. Hard reset to remote; if blocked by untracked files, remove and retry
        reset_result = _git_run(self.repo_path, ["reset", "--hard", remote_hash], check=False)
        if reset_result.returncode != 0:
            conflicting = _parse_untracked_reset_conflicts(reset_result.stderr)
            if conflicting:
                logger.warning(
                    "reset_blocked_by_untracked_files_removing",
                    file_count=len(conflicting),
                    files=conflicting,
                )
                for f in conflicting:
                    abs_path = os.path.join(self.repo_path, f)
                    try:
                        if os.path.isdir(abs_path) and not os.path.islink(abs_path):
                            shutil.rmtree(abs_path)
                        else:
                            os.remove(abs_path)
                    except Exception as exc:
                        logger.error(
                            "failed_to_remove_conflicting_untracked",
                            file=f,
                            error=str(exc),
                        )
                        raise
                _git_run(self.repo_path, ["reset", "--hard", remote_hash])
            else:
                err_msg = reset_result.stderr.strip() or "(no stderr output)"
                raise RuntimeError(
                    f"Git command failed in {self.repo_path}: "
                    f"git reset --hard {remote_hash}\n"
                    f"Error: {err_msg}"
                )

        # 4. If we stashed changes, apply and reconcile: keep only *new* files from stash
        if local_stash:
            apply_result = _git_run(self.repo_path, ["stash", "apply", local_stash], check=False)
            if apply_result.returncode != 0:
                logger.warning("stash_apply_had_conflicts", stderr=apply_result.stderr.strip())

            diff_result = _git_run(
                self.repo_path,
                ["diff", "--name-only", "--diff-filter=MD", f"{remote_hash}..{local_stash}"],
                check=False,
            )
            files_to_revert = [
                line.strip()
                for line in diff_result.stdout.strip().splitlines()
                if line.strip()
            ]
            if files_to_revert:
                logger.info(
                    "reverting_stash_changes_to_remote",
                    file_count=len(files_to_revert),
                    files=files_to_revert,
                )
                _git_run(self.repo_path, ["checkout", "HEAD", "--", *files_to_revert])

            _git_run(self.repo_path, ["stash", "drop", local_stash])

        post_local = self.get_commit_hash(self.branch)

        if pre_local == post_local:
            return GitUpdateResult(
                updated=False,
                local_commit=pre_local,
                remote_commit=post_local,
                message="Already up to date.",
            )

        return GitUpdateResult(
            updated=True,
            local_commit=pre_local,
            remote_commit=post_local,
            message=f"Synced from {pre_local} to {post_local} (remote preferred, new local files kept).",
        )
