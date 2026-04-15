"""PM2 process management wrappers."""

from __future__ import annotations

import shutil
import subprocess

from vcptoolbox_updater.utils import get_logger

logger = get_logger(__name__)


class Pm2Operator:
    def __init__(self, process_name: str, pm2_bin: str | None = None) -> None:
        self.process_name = process_name
        self.pm2_bin = pm2_bin or self._find_pm2()

    @staticmethod
    def _find_pm2() -> str:
        pm2 = shutil.which("pm2")
        if not pm2:
            raise RuntimeError("pm2 executable not found in PATH.")
        return pm2

    def _run(self, args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
        cmd = [self.pm2_bin, *args]
        logger.debug("running_pm2_command", command=" ".join(cmd))
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )

    def restart(self, cwd: str | None = None) -> str:
        result = self._run(["restart", self.process_name], cwd=cwd)
        stdout = result.stdout.strip()
        logger.info("pm2_restart_completed", process=self.process_name, stdout=stdout)
        return stdout

    def save(self) -> None:
        self._run(["save"])
        logger.info("pm2_save_completed")