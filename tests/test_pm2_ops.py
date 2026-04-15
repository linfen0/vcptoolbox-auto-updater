"""Unit tests for PM2 operations."""

from unittest.mock import MagicMock, patch

import pytest

from vcptoolbox_updater.pm2_ops import Pm2Operator


def test_find_pm2_success():
    with patch("vcptoolbox_updater.pm2_ops.shutil.which", return_value="C:\\npm\\pm2.cmd"):
        op = Pm2Operator("test-app")
        assert op.pm2_bin == "C:\\npm\\pm2.cmd"


def test_find_pm2_not_found():
    with patch("vcptoolbox_updater.pm2_ops.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="pm2 executable not found"):
            Pm2Operator("test-app")


def test_restart():
    op = Pm2Operator("test-app", pm2_bin="pm2")
    with patch.object(op, "_run", return_value=MagicMock(stdout="[PM2] test-app restarted")) as mock_run:
        output = op.restart(cwd="/tmp/repo")
        mock_run.assert_called_once_with(["restart", "test-app"], cwd="/tmp/repo")
        assert output == "[PM2] test-app restarted"


def test_save():
    op = Pm2Operator("test-app", pm2_bin="pm2")
    with patch.object(op, "_run", return_value=MagicMock()) as mock_run:
        op.save()
        mock_run.assert_called_once_with(["save"])
