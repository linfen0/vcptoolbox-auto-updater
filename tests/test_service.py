"""Tests for Windows service implementation."""

import os
import sys
from unittest.mock import patch

import pytest

from vcptoolbox_updater.service import AutoUpdaterService


class TestResolveConfigPath:
    def test_env_variable_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("VCPTOOLBOX_UPDATER_CONFIG", "C:\\custom\\config.yaml")
        assert AutoUpdaterService._resolve_config_path() == "C:\\custom\\config.yaml"

    def test_fallback_to_project_root(self):
        # When no env variable is set, it should resolve to the project root config.yaml
        result = AutoUpdaterService._resolve_config_path()
        assert result.endswith("config.yaml")
        # The parent directory of the config file should be the project root (parent of src/)
        config_dir = os.path.dirname(result)
        assert os.path.basename(config_dir) != "vcptoolbox_updater"
        # src/ directory should be inside the resolved project root
        assert os.path.isdir(os.path.join(config_dir, "src", "vcptoolbox_updater"))


class TestServiceClassAttributes:
    def test_exe_name_is_current_python(self):
        assert AutoUpdaterService._exe_name_ == sys.executable

    def test_exe_args_points_to_service_module(self):
        assert AutoUpdaterService._exe_args_ == "-m vcptoolbox_updater service"

    def test_svc_name(self):
        assert AutoUpdaterService._svc_name_ == "VCPToolBoxAutoUpdater"
