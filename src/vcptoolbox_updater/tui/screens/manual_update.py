"""Manual update screen."""

from __future__ import annotations

import asyncio
import sys

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Button, RichLog, Static

from vcptoolbox_updater.cli import _resolve_config_path
from vcptoolbox_updater.tui.i18n import _


class ManualUpdate(Screen[None]):
    """Screen to trigger a single manual update cycle."""

    NAME = "manual_update"

    CSS = """
    #update-card {
        width: 90%;
        height: 90%;
        background: rgba(40, 40, 55, 0.60);
        border: solid rgba(120, 180, 255, 0.35);
        padding: 1 2;
    }
    #title {
        text-align: center;
        text-style: bold;
        color: #a8d5ff;
        margin-bottom: 1;
    }
    RichLog {
        width: 100%;
        height: 1fr;
        background: rgba(20, 20, 30, 0.50);
        border: solid rgba(120, 180, 255, 0.30);
    }
    #features {
        margin-top: 1;
        color: rgba(200, 220, 255, 0.75);
    }
    #footer {
        text-align: center;
        margin-top: 1;
        color: rgba(180, 200, 230, 0.60);
    }
    Button {
        width: auto;
        margin-top: 1;
        background: rgba(80, 140, 220, 0.25);
        border: solid rgba(120, 180, 255, 0.40);
        color: #cce6ff;
    }
    Button:hover {
        background: rgba(100, 170, 255, 0.40);
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._running = False

    def compose(self) -> ComposeResult:
        with Container(id="update-card"):
            yield Static(_("update_title"), id="title")
            yield RichLog(highlight=False, id="log")
            yield Static(_("feat_merge"))
            yield Static(_("feat_pm2"))
            yield Static(_("feat_cli"))
            yield Static("")
            with Vertical():
                yield Button(_("update_run"), id="btn_run", variant="success")
                yield Button(_("back"), id="btn_back")
            yield Static("")
            yield Static(_("footer_keys"), id="footer")

    def on_mount(self) -> None:
        log_widget = self.query_one("#log", RichLog)
        log_widget.write(_("update_hint"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn_back":
            self.app.pop_screen()
            return
        if button_id == "btn_run":
            if self._running:
                self.notify(_("status_running"), severity="warning")
                return
            self._running = True
            log_widget = self.query_one("#log", RichLog)
            log_widget.clear()
            log_widget.write(_("update_starting"))
            asyncio.create_task(self._run_update())

    async def _run_update(self) -> None:
        log_widget = self.query_one("#log", RichLog)
        config_path = _resolve_config_path(None)
        try:
            cmd = [sys.executable, "-m", "vcptoolbox_updater", "-c", config_path, "update"]
            log_widget.write(f"> {' '.join(cmd)}")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            output = (stdout + stderr).decode("utf-8", errors="replace")
            for line in output.strip().splitlines():
                log_widget.write(line)
            if proc.returncode == 0:
                self.notify(_("update_success", message="更新完成"), severity="information")
            else:
                log_widget.write(_("update_fail", message=f"退出码 {proc.returncode}"))
                self.notify(_("update_fail", message=f"退出码 {proc.returncode}"), severity="error")
        except Exception as exc:
            log_widget.write(_("update_fail", message=str(exc)))
            self.notify(str(exc), severity="error")
        finally:
            self._running = False
