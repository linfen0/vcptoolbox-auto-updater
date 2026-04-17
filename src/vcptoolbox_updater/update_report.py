"""Update report dataclass (dependency-free)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UpdateReport:
    success: bool
    repo_path: str
    branch: str
    from_commit: str
    to_commit: str
    pm2_process: str
    pm2_output: str
    message: str
