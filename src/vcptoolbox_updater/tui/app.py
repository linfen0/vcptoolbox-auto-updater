from __future__ import annotations

from textual.app import App, ComposeResult

from vcptoolbox_updater.tui.i18n import _
from vcptoolbox_updater.tui.screens.log_viewer import LogViewer
from vcptoolbox_updater.tui.screens.main_menu import MainMenu
from vcptoolbox_updater.tui.screens.manual_update import ManualUpdate
from vcptoolbox_updater.tui.screens.service_manager import ServiceManager


class UpdaterTuiApp(App[None]):
    """Lightweight Textual TUI for managing the VCPToolBox Auto Updater service."""

    CSS = """
    Screen {
        align: center top;
        background: rgba(20, 20, 30, 0.75);
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Toggle Dark"),
        ("escape", "pop_screen", "Back"),
    ]

    SCREENS = {
        "main_menu": MainMenu,
        "log_viewer": LogViewer,
        "service_manager": ServiceManager,
        "manual_update": ManualUpdate,
    }

    def on_mount(self) -> None:
        self.title = _("app_name")
        self.push_screen("main_menu")

    async def action_pop_screen(self) -> None:
        if len(self.screen_stack) > 1:
            await super().action_pop_screen()

    def action_toggle_dark(self) -> None:
        self.theme = "textual-dark" if self.theme == "textual-light" else "textual-light"
