"""Unit tests for CLI."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from vcptoolbox_updater.cli import _resolve_config_path, cli


def test_resolve_config_path_explicit():
    assert _resolve_config_path("/tmp/custom.yaml") == "/tmp/custom.yaml"


def test_resolve_config_path_env():
    with patch.dict(os.environ, {"VCPTOOLBOX_UPDATER_CONFIG": "/tmp/env.yaml"}):
        assert _resolve_config_path(None) == "/tmp/env.yaml"


def test_resolve_config_path_default():
    with patch.dict(os.environ, {}, clear=True):
        result = _resolve_config_path(None)
        assert result.endswith("config.yaml")


def _make_mock_cfg():
    mock_cfg = MagicMock()
    mock_cfg.git.repo_path = Path("/tmp/repo")
    mock_cfg.git.remote_name = "origin"
    mock_cfg.git.branch = "main"
    mock_cfg.git.check_interval_hours = 24.0
    mock_cfg.pm2.process_name = "test-app"
    mock_cfg.pm2.pm2_bin = None
    mock_cfg.notifications.feishu.enabled = False
    mock_cfg.notifications.wecom.enabled = False
    mock_cfg.notifications.email.enabled = False
    mock_cfg.log_level = "INFO"
    mock_cfg.log_file = None
    return mock_cfg


def test_cli_update_no_update():
    runner = CliRunner()
    mock_git_result = MagicMock()
    mock_git_result.updated = False
    mock_git_result.local_commit = "abc1234"
    mock_git_result.remote_commit = "abc1234"

    with patch("vcptoolbox_updater.cli.load_config", return_value=_make_mock_cfg()), \
         patch("vcptoolbox_updater.cli.GitOperator") as mock_git_op_cls, \
         patch("vcptoolbox_updater.cli.configure_logging"):
        mock_git_op = MagicMock()
        mock_git_op.pull_and_resolve_conflicts.return_value = mock_git_result
        mock_git_op_cls.return_value = mock_git_op
        result = runner.invoke(cli, ["--config", "/tmp/cfg.yaml", "update"])
        assert result.exit_code == 0
        assert "No update needed" in result.output


def test_cli_update_with_update():
    runner = CliRunner()
    mock_git_result = MagicMock()
    mock_git_result.updated = True
    mock_git_result.local_commit = "abc1234"
    mock_git_result.remote_commit = "def5678"
    mock_git_result.message = "Updated"

    with patch("vcptoolbox_updater.cli.load_config", return_value=_make_mock_cfg()), \
         patch("vcptoolbox_updater.cli.GitOperator") as mock_git_op_cls, \
         patch("vcptoolbox_updater.cli.Pm2Operator") as mock_pm2_op_cls, \
         patch("vcptoolbox_updater.cli.configure_logging"):
        mock_git_op = MagicMock()
        mock_git_op.pull_and_resolve_conflicts.return_value = mock_git_result
        mock_git_op_cls.return_value = mock_git_op
        mock_pm2_op = MagicMock()
        mock_pm2_op.restart.return_value = "PM2 restarted"
        mock_pm2_op_cls.return_value = mock_pm2_op
        result = runner.invoke(cli, ["--config", "/tmp/cfg.yaml", "update"])
        assert result.exit_code == 0
        assert "Updated" in result.output
        mock_pm2_op.restart.assert_called_once_with(cwd=str(Path("/tmp/repo")))


def test_cli_update_failure():
    runner = CliRunner()
    with patch("vcptoolbox_updater.cli.load_config", return_value=_make_mock_cfg()), \
         patch("vcptoolbox_updater.cli.GitOperator") as mock_git_op_cls, \
         patch("vcptoolbox_updater.cli.configure_logging"):
        mock_git_op = MagicMock()
        mock_git_op.pull_and_resolve_conflicts.side_effect = RuntimeError("git error")
        mock_git_op_cls.return_value = mock_git_op
        result = runner.invoke(cli, ["--config", "/tmp/cfg.yaml", "update"])
        assert result.exit_code == 0
        assert "Update failed" in result.output
