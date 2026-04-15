"""Git operations: fetch, compare, hard-reset merge."""

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
        if status_result.stdout.strip():
            logger.warning("local_changes_detected_stashing")
            self._run(["stash", "push", "-m", "auto-updater-stash"], check=False)

        reset_result = self._run(["reset", "--hard", self.remote_ref])
        logger.info(
            "git_hard_reset_completed",
            from_commit=result.local_commit,
            to_commit=result.remote_commit,
            stdout=reset_result.stdout.strip(),
        )

        post_local = self.get_commit_hash(self.branch)
        return GitUpdateResult(
            updated=True,
            local_commit=pre_local,
            remote_commit=post_local,
            message=f"Hard reset from {pre_local} to {post_local}.",
        )