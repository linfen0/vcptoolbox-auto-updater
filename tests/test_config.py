"""Unit tests for configuration."""

import tempfile
from pathlib import Path

from vcptoolbox_updater.config import load_config


def test_load_config():
    yaml_content = """
repo_path: /tmp/test-repo

git:
  remote_name: origin
  branch: develop
  check_interval_hours: 12.0

pm2:
  processes:
    - name: test-app
      script: app.js
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        cfg = load_config(Path(f.name))

    assert cfg.repo_path == Path("/tmp/test-repo")
    assert cfg.git.branch == "develop"
    assert cfg.git.check_interval_hours == 12.0
    assert len(cfg.pm2.processes) == 1
    assert cfg.pm2.processes[0].name == "test-app"
    assert cfg.pm2.processes[0].script == "app.js"
    assert cfg.notifications.feishu.enabled is False


def test_load_config_with_processes():
    yaml_content = """
repo_path: /tmp/test-repo

git:
  remote_name: origin
  branch: develop
  check_interval_hours: 12.0

pm2:
  processes:
    - name: vcp-main
      script: server.js
      watch: false
      max_memory_restart: "1500M"
      kill_timeout: 15000
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        cfg = load_config(Path(f.name))

    assert cfg.repo_path == Path("/tmp/test-repo")
    assert len(cfg.pm2.processes) == 1
    assert cfg.pm2.processes[0].name == "vcp-main"
    assert cfg.pm2.processes[0].script == "server.js"
    assert cfg.pm2.processes[0].max_memory_restart == "1500M"
    assert cfg.pm2.processes[0].kill_timeout == 15000