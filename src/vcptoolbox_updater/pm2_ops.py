"""PM2 process management wrappers."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from vcptoolbox_updater.config import Pm2Config
from vcptoolbox_updater.utils import get_logger

logger = get_logger(__name__)


def _find_pm2() -> str:
    pm2 = shutil.which("pm2")
    if not pm2:
        raise RuntimeError("pm2 executable not found in PATH.")
    return pm2


def _run_pm2(pm2_bin: str, args: list[str], cwd: str | None = None) -> str:
    cmd = [pm2_bin, *args]
    logger.debug("running_pm2_command", command=" ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _start_or_restart(pm2_bin: str, ecosystem: dict, cwd: str | None = None) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(ecosystem, f, ensure_ascii=False)
        temp_path = f.name

    try:
        stdout = _run_pm2(pm2_bin, ["startOrRestart", temp_path], cwd=cwd)
        logger.info("pm2_start_or_restart_completed", stdout=stdout)
        return stdout
    finally:
        Path(temp_path).unlink(missing_ok=True)


class Pm2Operator:
    def __init__(
        self,
        pm2_bin: str | None = None,
        pm2_cfg: Pm2Config | None = None,
    ) -> None:
        self.pm2_cfg = pm2_cfg
        self.pm2_bin = pm2_bin or _find_pm2()

    def restart(self, cwd: str | None = None) -> str:
        if not self.pm2_cfg or not self.pm2_cfg.processes:
            raise RuntimeError("No PM2 processes configured.")

        ecosystem = self.pm2_cfg.to_ecosystem_dict(default_cwd=cwd)
        return _start_or_restart(self.pm2_bin, ecosystem, cwd=cwd)

    def save(self) -> None:
        _run_pm2(self.pm2_bin, ["save"])
        logger.info("pm2_save_completed")
