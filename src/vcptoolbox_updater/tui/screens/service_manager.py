"""Service manager screen for Windows service operations."""

from __future__ import annotations

import subprocess
import sys

from textual.app import ComposeResult
from textual.containers import Container, Grid
from textual.screen import Screen
from textual.widgets import Button, Static

from vcptoolbox_updater.tui.i18n import _


class ServiceManager(Screen[None]):
    """Screen to install/start/stop/uninstall the Windows service."""

    NAME = "service_manager"

    CSS = """
    #service-card {
        width: 72;
        height: auto;
        background: rgba(40, 40, 55, 0.60);
        border: solid rgba(120, 180, 255, 0.35);
        padding: 2 3;
    }
    #title {
        text-align: center;
        text-style: bold;
        color: #a8d5ff;
        margin-bottom: 1;
    }
    #status {
        text-align: center;
        margin: 1 0;
        color: #7ecfff;
    }
    Grid {
        grid-size: 2;
        grid-gutter: 1;
    }
    Button {
        width: 100%;
        margin: 1 0;
        background: rgba(80, 140, 220, 0.25);
        border: solid rgba(120, 180, 255, 0.40);
        color: #cce6ff;
    }
    Button:hover {
        background: rgba(100, 170, 255, 0.40);
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
    """

    def compose(self) -> ComposeResult:
        with Container(id="service-card"):
            yield Static(_("service_title"), id="title")
            yield Static(_("status_ready"), id="status")
            with Grid():
                yield Button(_("service_install"), id="btn_install")
                yield Button(_("service_uninstall"), id="btn_uninstall", variant="error")
                yield Button(_("service_start"), id="btn_start", variant="success")
                yield Button(_("service_stop"), id="btn_stop", variant="warning")
            yield Static("")
            yield Static(_("feat_service"))
            yield Static(_("feat_cli"))
            yield Static("")
            yield Static(_("footer_keys"), id="footer")
            yield Button(_("back"), id="back-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "back-btn":
            self.app.pop_screen()
            return

        command_map = {
            "btn_install": "install",
            "btn_uninstall": "uninstall",
            "btn_start": "start",
            "btn_stop": "stop",
        }
        cmd = command_map.get(button_id)
        if cmd is None:
            return

        status = self.query_one("#status", Static)
        status.update(_("status_running"))
        self._run_service_command(cmd)

    def _run_service_command(self, cmd: str) -> None:
        status = self.query_one("#status", Static)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "vcptoolbox_updater", cmd],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            output = (result.stdout + result.stderr).strip() or _("status_done")
            status.update(_("service_result", action=cmd.capitalize(), output=output))
            if result.returncode == 0:
                self.notify(_("service_succeeded", action=cmd.capitalize()), severity="information")
            else:
                self.notify(_("service_failed", action=cmd.capitalize()), severity="error")
        except Exception as exc:
            status.update(f"{_('status_error')}: {exc}")
            self.notify(str(exc), severity="error")
