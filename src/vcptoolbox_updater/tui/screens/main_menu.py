"""Main menu screen for the TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Static

from vcptoolbox_updater.cli import _resolve_config_path
from vcptoolbox_updater.config import load_config
from vcptoolbox_updater.tui.i18n import _


class MainMenu(Screen[None]):
    """Main menu with navigation buttons and feature highlights."""

    NAME = "main_menu"

    CSS = """
    #main-card {
        width: 74;
        height: 95%;
        background: rgba(40, 40, 55, 0.60);
        border: solid rgba(120, 180, 255, 0.35);
        padding: 2 3;
        margin-top: 1;
        layout: vertical;
    }
    #title {
        text-align: center;
        text-style: bold;
        color: #a8d5ff;
        margin-bottom: 1;
    }
    #desc {
        text-align: center;
        color: rgba(200, 220, 255, 0.80);
        margin-bottom: 1;
    }
    #repo {
        text-align: center;
        color: #7ecfff;
        margin-bottom: 1;
    }
    #scroll-body {
        height: 1fr;
        min-height: 10;
    }
    #workflow {
        text-align: left;
        color: rgba(220, 230, 255, 0.85);
        margin: 1 0;
        padding: 0 1;
        background: rgba(60, 70, 100, 0.35);
        border: solid rgba(120, 180, 255, 0.25);
        height: auto;
    }
    #workflow-title {
        text-style: bold;
        color: #a8d5ff;
        margin: 0 0;
    }
    .btn-hint {
        text-align: left;
        color: rgba(200, 220, 255, 0.70);
        margin: 0 0 1 2;
    }
    #buttons {
        height: auto;
        margin: 1 0;
    }
    Button {
        width: 100%;
        margin: 0 0;
        background: rgba(80, 140, 220, 0.25);
        border: solid rgba(120, 180, 255, 0.40);
        color: #cce6ff;
    }
    Button:hover {
        background: rgba(100, 170, 255, 0.40);
    }
    .features {
        margin: 0 0;
        color: rgba(200, 220, 255, 0.75);
    }
    #footer {
        text-align: center;
        margin: 0 0;
        color: rgba(180, 200, 230, 0.60);
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="main-card"):
            yield Static(_("menu_title"), id="title")
            yield Static(_("menu_desc"), id="desc")
            yield Static(_("menu_repo") + ": ...", id="repo")
            with VerticalScroll(id="scroll-body"):
                with Vertical(id="workflow"):
                    yield Static(_("workflow_title"), id="workflow-title")
                    yield Static(_("workflow_step1"))
                    yield Static(_("workflow_step2"))
                    yield Static(_("workflow_step3"))
                    yield Static(_("workflow_step4"))
                with Vertical(id="buttons"):
                    yield Button(_("menu_logs"), id="btn_logs")
                    yield Static(_("hint_logs"), classes="btn-hint")
                    yield Button(_("menu_service"), id="btn_service")
                    yield Static(_("hint_service"), classes="btn-hint")
                    yield Button(_("menu_update"), id="btn_update")
                    yield Static(_("hint_update"), classes="btn-hint")
                    yield Button(_("menu_quit"), id="btn_quit", variant="error")
                    yield Static(_("hint_quit"), classes="btn-hint")
            yield Static("")
            yield Static(_("footer_keys"), id="footer")

    def on_mount(self) -> None:
        self.run_worker(self._load_repo_path)

    async def _load_repo_path(self) -> None:
        try:
            config_path = _resolve_config_path(None)
            cfg = load_config(config_path)
            repo = str(cfg.repo_path)
        except Exception as exc:
            repo = f"(error: {exc})"
        self.query_one("#repo", Static).update(f"{_('menu_repo')}: {repo}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn_logs":
            self.app.push_screen("log_viewer")
        elif button_id == "btn_service":
            self.app.push_screen("service_manager")
        elif button_id == "btn_update":
            self.app.push_screen("manual_update")
        elif button_id == "btn_quit":
            self.app.exit()
