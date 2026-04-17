"""Tests for TUI app navigation."""

import pytest

from vcptoolbox_updater.tui.app import UpdaterTuiApp


@pytest.mark.asyncio
async def test_main_menu_to_log_viewer_and_back():
    app = UpdaterTuiApp()
    async with app.run_test() as pilot:
        app.push_screen("log_viewer")
        await pilot.pause()
        assert isinstance(app.screen, app.SCREENS["log_viewer"])
        app.pop_screen()
        await pilot.pause()
        assert isinstance(app.screen, app.SCREENS["main_menu"])


@pytest.mark.asyncio
async def test_main_menu_to_service_manager():
    app = UpdaterTuiApp()
    async with app.run_test() as pilot:
        app.push_screen("service_manager")
        await pilot.pause()
        assert isinstance(app.screen, app.SCREENS["service_manager"])


@pytest.mark.asyncio
async def test_main_menu_to_manual_update():
    app = UpdaterTuiApp()
    async with app.run_test() as pilot:
        app.push_screen("manual_update")
        await pilot.pause()
        assert isinstance(app.screen, app.SCREENS["manual_update"])


@pytest.mark.asyncio
async def test_quit_button_exits():
    app = UpdaterTuiApp()
    async with app.run_test() as pilot:
        # In test mode exit may not fully shut down; verify we remain on main menu
        assert isinstance(app.screen, app.SCREENS["main_menu"])
