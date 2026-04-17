"""Tests for service manager screen."""

from unittest.mock import MagicMock, patch

import pytest

from textual.app import App

from vcptoolbox_updater.tui.screens.service_manager import ServiceManager


class _TestApp(App[None]):
    pass


@pytest.mark.asyncio
async def test_service_manager_install_button():
    app = _TestApp()
    screen = ServiceManager()
    async with app.run_test() as pilot:
        app.install_screen(screen, name="service_manager")
        app.push_screen("service_manager")
        await pilot.pause()
        with patch("vcptoolbox_updater.tui.screens.service_manager.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="installed", stderr="", returncode=0)
            screen._run_service_command("install")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[-2:] == ["vcptoolbox_updater", "install"]
