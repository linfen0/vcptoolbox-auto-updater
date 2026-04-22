"""Tests for manual update screen."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vcptoolbox_updater.tui.app import UpdaterTuiApp
from vcptoolbox_updater.tui.screens.manual_update import ManualUpdate


@pytest.mark.asyncio
async def test_manual_update_click_starts_worker():
    app = UpdaterTuiApp()
    async with app.run_test() as pilot:
        app.push_screen("manual_update")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ManualUpdate)

        # Mock run_worker to verify it gets called
        original_run_worker = screen.run_worker
        worker_called = False

        def mock_run_worker(coroutine, **kwargs):
            nonlocal worker_called
            worker_called = True
            # Don't actually run the worker to avoid side effects
            return MagicMock()

        screen.run_worker = mock_run_worker

        # Click the run button
        btn = screen.query_one("#btn_run")
        btn.press()
        await pilot.pause()

        assert worker_called is True
        assert screen._update_running is True


@pytest.mark.asyncio
async def test_manual_update_worker_failure_resets_flag():
    app = UpdaterTuiApp()
    async with app.run_test() as pilot:
        app.push_screen("manual_update")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ManualUpdate)

        # Simulate an exception inside _run_update by patching asyncio.create_subprocess_exec
        with patch(
            "vcptoolbox_updater.tui.screens.manual_update.asyncio.create_subprocess_exec",
            side_effect=RuntimeError("boom"),
        ):
            btn = screen.query_one("#btn_run")
            btn.press()
            await pilot.pause()
            # Allow worker to process
            await asyncio.sleep(0.5)

        assert screen._update_running is False
