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
    files: list[str] = []
    line_iter = iter(stderr.splitlines())

    # Locate the header that announces the conflict block.
    for line in line_iter:
        if "would be overwritten by checkout:" in line.strip():
            break
    else:
        return files

    # Consume indented file paths until a blank or non-indented line.
    for line in line_iter:
        stripped = line.strip()
        if not stripped or not line.startswith(("\t", " ")):
            break
        files.append(stripped)

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


def _git_run(
    repo_path: str,
    cmd: list[str],
    check: bool = True,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute a git sub-process and return its result.

    Args:
        repo_path: Path to the git repository (used as *cwd*).
        cmd: Git sub-command arguments (e.g. ``["fetch", "origin"]``).
        check: When ``True`` (default), raise ``RuntimeError`` on non-zero exit.
        input: Optional string to feed to the command's standard input.

    Returns:
        The completed process object.

    Raises:
        RuntimeError: If *check* is ``True`` and the command exits with a non-zero code.
    """
    full_cmd = ["git", *cmd]
    logger.debug("running_git_command", command=" ".join(full_cmd), cwd=repo_path)
    # Force English output so that stderr parsing (e.g. untracked conflict
    # detection) is locale-independent.
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["LANGUAGE"] = "en"
    result = subprocess.run(
        full_cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        input=input,
        env=env,
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

    def _ensure_git_config(self) -> None:
        """Configure Git to avoid Windows-specific path and encoding issues.

        Sets *core.longpaths* so that file paths longer than the legacy
        Windows MAX_PATH limit (260 characters) are handled correctly, and
        *core.quotepath* so that non-ASCII file names are shown verbatim
        instead of octal-escaped strings.
        """
        for key, value in (("core.longpaths", "true"), ("core.quotepath", "false")):
            result = _git_run(self.repo_path, ["config", key], check=False)
            current = result.stdout.strip() if result.returncode == 0 else ""
            if current != value:
                _git_run(self.repo_path, ["config", key, value])
                logger.info("git_config_set", key=key, value=value, previous=current or None)

    def fetch(self) -> None:
        """Run ``git fetch <remote_name>`` for the configured remote."""
        self._ensure_git_config()
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

    def is_detached_head(self) -> bool:
        """Check whether the repository is currently in a detached HEAD state.

        Returns:
            ``True`` if ``HEAD`` is detached (not pointing to a branch).
        """
        result = _git_run(self.repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip() == "HEAD"

    def check_update_needed(self) -> GitUpdateResult:
        """Determine whether the local HEAD is behind the remote.

        Uses ``HEAD`` (not the branch name) so that detached-HEAD states are
        compared against the remote correctly.

        Returns:
            A :class:`GitUpdateResult` describing the comparison outcome.
        """
        local_commit = self.get_commit_hash("HEAD")
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
            ["merge-base", "is-ancestor", self.remote_ref, "HEAD"],
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
                ["rev-list", "--count", f"HEAD..{self.remote_ref}"],
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

    def _stash_local_changes(self) -> str | None:
        """Stash local tracked changes if any exist.

        Adds all tracked changes to the index and pushes them onto the stash
        stack when the working tree is dirty with respect to tracked files.

        Returns:
            Stash reference (e.g. ``"stash@{0}"``) if changes were stashed,
            otherwise ``None``.
        """
        _git_run(self.repo_path, ["add", "-u"])
        status_result = _git_run(self.repo_path, ["status", "--porcelain"], check=False)
        has_tracked = any(
            line and not line.startswith("?")
            for line in status_result.stdout.strip().splitlines()
        )
        if not has_tracked:
            return None
        _git_run(self.repo_path, ["stash", "push", "-m", "local"])
        local_stash = "stash@{0}"
        logger.info("local_tracked_changes_stashed", stash=local_stash)
        return local_stash

    def _checkout_branch_if_detached(self) -> None:
        """Checkout the configured branch when in a detached HEAD state."""
        if self.is_detached_head():
            logger.warning("detached_head_checking_out", branch=self.branch)
            _git_run(self.repo_path, ["checkout", self.branch])
            logger.info("checked_out_branch", branch=self.branch)

    def _hard_reset_with_retry(self, remote_hash: str) -> None:
        """Hard-reset to *remote_hash*, removing untracked conflicts once if needed.

        If ``git reset --hard`` aborts because untracked files would be
        overwritten, the conflicting files are removed and the reset is
        retried **once**.

        Args:
            remote_hash: The commit hash to reset to.

        Raises:
            RuntimeError: If the reset fails for a reason other than untracked
                file collisions, or if the retry also fails.
        """
        result = _git_run(
            self.repo_path, ["reset", "--hard", remote_hash], check=False
        )
        if result.returncode == 0:
            return

        conflicting = _parse_untracked_reset_conflicts(result.stderr)
        if not conflicting:
            err_msg = result.stderr.strip() or "(no stderr output)"
            raise RuntimeError(
                f"Git command failed in {self.repo_path}: "
                f"git reset --hard {remote_hash}\n"
                f"Error: {err_msg}"
            )

        logger.warning(
            "reset_blocked_by_untracked_files_removing",
            file_count=len(conflicting),
            files=conflicting,
        )
        for f in conflicting:
            self._remove_untracked_path(f)

        _git_run(self.repo_path, ["reset", "--hard", remote_hash])

    def _remove_untracked_path(self, rel_path: str) -> None:
        abs_path = os.path.join(self.repo_path, rel_path)
        try:
            if os.path.isdir(abs_path) and not os.path.islink(abs_path):
                shutil.rmtree(abs_path)
            else:
                os.remove(abs_path)
        except Exception as exc:
            logger.error(
                "failed_to_remove_conflicting_untracked",
                file=rel_path,
                error=str(exc),
            )
            raise

    def _apply_and_reconcile_stash(self, local_stash: str, remote_hash: str) -> None:
        """Apply the stash and reconcile so only *new* local files survive.

        Modified or deleted files from the stash are reverted to the remote
        (HEAD) version; added files are kept as-is.  Tree conflicts are
        resolved by taking the HEAD version (or removing the file if it does
        not exist in HEAD).  The stash is dropped afterwards.

        Args:
            local_stash: Reference to the stash to apply (e.g. ``"stash@{0}"``).
            remote_hash: The commit hash that represents the remote state.
        """
        apply_result = _git_run(
            self.repo_path, ["stash", "apply", local_stash], check=False
        )
        if apply_result.returncode != 0:
            logger.warning(
                "stash_apply_had_conflicts", stderr=apply_result.stderr.strip()
            )

        # Gather all files that should be reverted to HEAD (modified/deleted
        # from the stash plus any unmerged files caused by tree conflicts).
        #处理树冲突
        def _name_set(*args: str) -> set[str]:
            result = _git_run(self.repo_path, list(args), check=False)
            return {
                line.strip()
                for line in result.stdout.strip().splitlines()
                if line.strip()
            }

        files_to_revert = _name_set(
            "diff", "--name-only", "--diff-filter=MD", f"{remote_hash}..{local_stash}"
        )
        unmerged_files = _name_set("diff", "--name-only", "--diff-filter=U")
        all_files = files_to_revert | unmerged_files

        if not all_files:
            _git_run(self.repo_path, ["stash", "drop", local_stash])
            return

        # Determine which files actually exist in HEAD so we never attempt an
        # illegal ``git checkout HEAD --`` on a path that is not present.
        head_files = _name_set("ls-tree", "-r", "HEAD", "--name-only")

        checkout_files = sorted(f for f in all_files if f in head_files)
        if checkout_files:
            logger.info(
                "reverting_stash_changes_to_remote",
                file_count=len(checkout_files),
                files=checkout_files,
            )
            _git_run(
                self.repo_path,
                ["checkout", "HEAD", "--pathspec-from-file=-"],
                input="\n".join(checkout_files),
            )

        # Unmerged files that do not exist in HEAD must be removed to clear
        # the conflict state.
        to_remove = sorted(f for f in unmerged_files if f not in head_files)
        if to_remove:
            logger.info(
                "removing_unmerged_files_not_in_head",
                file_count=len(to_remove),
                files=to_remove,
            )
            _git_run(
                self.repo_path,
                ["rm", "-f", "--ignore-unmatch", *to_remove],
                check=False,
            )

        _git_run(self.repo_path, ["stash", "drop", local_stash])

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

        local_stash = self._stash_local_changes()
        self._checkout_branch_if_detached()
        self._hard_reset_with_retry(remote_hash)
        if local_stash:
            self._apply_and_reconcile_stash(local_stash, remote_hash)

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
