"""Git operations: fetch, compare, and merge preferring remote on conflicts."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from vcptoolbox_updater.utils import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class GitUpdateResult:
    updated: bool
    local_commit: str
    remote_commit: str
    message: str


class GitOperator:
    def __init__(self, repo_path: str, remote_name: str, branch: str) -> None:
        self.repo_path = repo_path
        self.remote_name = remote_name
        self.branch = branch
        self.remote_ref = f"{remote_name}/{branch}"

    def _run(self, cmd: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        full_cmd = ["git", *cmd]
        logger.debug("running_git_command", command=" ".join(full_cmd), cwd=cwd or self.repo_path)
        result = subprocess.run(
            full_cmd,
            cwd=cwd or self.repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if check and result.returncode != 0:
            err_msg = result.stderr.strip() or "(no stderr output)"
            raise RuntimeError(
                f"Git command failed in {cwd or self.repo_path}: "
                f"{' '.join(full_cmd)}\n"
                f"Error: {err_msg}"
            )
        return result

    def fetch(self) -> None:
        result = self._run(["fetch", self.remote_name])
        logger.info("git_fetch_completed", stdout=result.stdout.strip())

    def get_commit_hash(self, ref: str) -> str:
        result = self._run(["rev-parse", "--short", ref])
        return result.stdout.strip()

    def check_update_needed(self) -> GitUpdateResult:
        local_commit = self.get_commit_hash(self.branch)
        remote_commit = self.get_commit_hash(self.remote_ref)

        if local_commit == remote_commit:
            return GitUpdateResult(
                updated=False,
                local_commit=local_commit,
                remote_commit=remote_commit,
                message="Already up to date.",
            )

        # Check whether remote is an ancestor of local (i.e. local already contains all remote commits)
        ancestor_result = self._run(
            ["merge-base", "--is-ancestor", self.remote_ref, self.branch],
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
            count_result = self._run(
                ["rev-list", "--count", f"{self.branch}..{self.remote_ref}"]
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

    def is_detached_head(self) -> bool:
        result = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip() == "HEAD"

    def checkout_branch(self) -> None:
        self._run(["checkout", self.branch])
        logger.info("checked_out_branch", branch=self.branch)

    def pull_and_resolve_conflicts(self) -> GitUpdateResult:
        pre_local = self.get_commit_hash(self.branch)
        self.fetch()

        detached = False
        if self.is_detached_head():
            logger.warning("detached_head_detected", branch=self.branch)
            self.checkout_branch()
            pre_local = self.get_commit_hash(self.branch)
            detached = True

        result = self.check_update_needed()
        if not result.updated and not detached:
            return result

        if not result.updated and detached:
            return GitUpdateResult(
                updated=True,
                local_commit=pre_local,
                remote_commit=pre_local,
                message="Detached HEAD fixed, no new commits. Restart required.",
            )

        status_result = self._run(["status", "--porcelain"], check=False)
        tracked_changes = [line for line in status_result.stdout.strip().splitlines() if line and not line.startswith("?")]
        untracked_files = [line[3:].strip() for line in status_result.stdout.strip().splitlines() if line.startswith("?")]

        if tracked_changes:
            logger.warning("local_changes_detected_committing", file_count=len(tracked_changes))
            self._run(["add", "-u"])
            self._run(["commit", "-m", "auto-updater: preserve local changes"])

        if untracked_files:
            logger.warning("untracked_files_detected", file_count=len(untracked_files), files=untracked_files)

        merge_result = self._run(
            ["merge", "-X", "theirs", self.remote_ref],
            check=False,
        )
        if merge_result.returncode != 0:
            logger.warning(
                "merge_conflicts_detected_preferring_remote",
                stdout=merge_result.stdout.strip(),
                stderr=merge_result.stderr.strip(),
            )
            self._run(["checkout", "--theirs", "."])
            self._run(["add", "-u"])
            self._run(["commit", "-m", f"Merge {self.remote_ref} (prefer remote changes)"])
        else:
            logger.info(
                "git_merge_completed",
                from_commit=result.local_commit,
                to_commit=result.remote_commit,
                stdout=merge_result.stdout.strip(),
            )

        post_local = self.get_commit_hash(self.branch)
        return GitUpdateResult(
            updated=True,
            local_commit=pre_local,
            remote_commit=post_local,
            message=f"Merged from {pre_local} to {post_local} (remote preferred on conflicts).",
        )