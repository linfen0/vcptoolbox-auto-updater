"""Unit tests for PM2 operations."""

from unittest.mock import patch

import pytest

from vcptoolbox_updater.config import Pm2Config, Pm2ProcessConfig
from vcptoolbox_updater import pm2_ops


def test_find_pm2_success():
    with patch("vcptoolbox_updater.pm2_ops.shutil.which", return_value="C:\\npm\\pm2.cmd"):
        op = pm2_ops.Pm2Operator()
        assert op.pm2_bin == "C:\\npm\\pm2.cmd"


def test_find_pm2_not_found():
    with patch("vcptoolbox_updater.pm2_ops.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="pm2 executable not found"):
            pm2_ops.Pm2Operator()


def test_restart_runs_start_or_restart_for_all_processes():
    cfg = Pm2Config(processes=[Pm2ProcessConfig(name="vcp-main", script="server.js")])
    op = pm2_ops.Pm2Operator(pm2_bin="pm2", pm2_cfg=cfg)
    with patch.object(pm2_ops, "_start_or_restart", return_value="[PM2] all ok") as mock_sor:
        output = op.restart(cwd="/tmp/repo")
        mock_sor.assert_called_once_with("pm2", cfg.to_ecosystem_dict(default_cwd="/tmp/repo"), cwd="/tmp/repo")
        assert output == "[PM2] all ok"


def test_restart_no_processes_raises():
    op = pm2_ops.Pm2Operator(pm2_bin="pm2", pm2_cfg=Pm2Config(processes=[]))
    with pytest.raises(RuntimeError, match="No PM2 processes configured"):
        op.restart()


def test_restart_no_config_raises():
    op = pm2_ops.Pm2Operator(pm2_bin="pm2", pm2_cfg=None)
    with pytest.raises(RuntimeError, match="No PM2 processes configured"):
        op.restart()


def test_save():
    op = pm2_ops.Pm2Operator(pm2_bin="pm2")
    with patch.object(pm2_ops, "_run_pm2", return_value="") as mock_run:
        op.save()
        mock_run.assert_called_once_with("pm2", ["save"])


def test_to_ecosystem_dict():
    proc = Pm2ProcessConfig(
        name="vcp-main",
        script="server.js",
        watch=False,
        max_memory_restart="1500M",
        kill_timeout=15000,
    )
    config = proc.to_ecosystem_dict()
    assert config["name"] == "vcp-main"
    assert config["script"] == "server.js"
    assert config["max_memory_restart"] == "1500M"
    assert config["kill_timeout"] == 15000
    assert "args" not in config


def test_pm2_config_to_ecosystem_dict():
    cfg = Pm2Config(
        processes=[
            Pm2ProcessConfig(name="vcp-main", script="server.js"),
            Pm2ProcessConfig(name="vcp-admin", script="adminServer.js"),
        ]
    )
    ecosystem = cfg.to_ecosystem_dict()
    assert len(ecosystem["apps"]) == 2
    assert ecosystem["apps"][0]["name"] == "vcp-main"
    assert ecosystem["apps"][1]["name"] == "vcp-admin"
