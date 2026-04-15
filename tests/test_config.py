"""Unit tests for configuration."""

import tempfile
from pathlib import Path

from vcptoolbox_updater.config import load_config


def test_load_config():
    yaml_content = """
git:
  repo_path: /tmp/test-repo
  remote_name: origin
  branch: develop
  check_interval_hours: 12.0

pm2:
  process_name: test-app
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        cfg = load_config(Path(f.name))

    assert cfg.git.repo_path == Path("/tmp/test-repo")
    assert cfg.git.branch == "develop"
    assert cfg.git.check_interval_hours == 12.0
    assert cfg.pm2.process_name == "test-app"
    assert cfg.notifications.feishu.enabled is False