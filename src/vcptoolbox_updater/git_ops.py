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
        return subprocess.run(
            full_cmd,
            cwd=cwd or self.repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=check,
        )

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

    def pull_and_resolve_conflicts(self) -> GitUpdateResult:
        pre_local = self.get_commit_hash(self.branch)
        self.fetch()

        result = self.check_update_needed()
        if not result.updated:
            return result

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