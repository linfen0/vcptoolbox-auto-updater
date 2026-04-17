"""Tests for log viewer screen."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from textual.app import App

from vcptoolbox_updater.tui.screens.log_viewer import LogViewer


class _TestApp(App[None]):
    pass


@pytest.mark.asyncio
async def test_log_viewer_displays_log_content():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
        f.write("line1\nline2\nline3\n")
        log_path = f.name

    mock_cfg = type("MockCfg", (), {"log_file": Path(log_path), "repo_path": Path("/tmp")})()
    with patch("vcptoolbox_updater.tui.screens.log_viewer.load_config", return_value=mock_cfg):
        app = _TestApp()
        screen = LogViewer()
        async with app.run_test() as pilot:
            app.install_screen(screen, name="log_viewer")
            app.push_screen("log_viewer")
            await pilot.pause()
            log_widget = screen.query_one("#log")
            content = log_widget.lines
            assert any("line1" in str(line) for line in content)
            assert any("line3" in str(line) for line in content)
            screen.on_unmount()
