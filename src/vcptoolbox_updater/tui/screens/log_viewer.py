"""Log viewer screen with live tail."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Label, RichLog, Static

from vcptoolbox_updater.cli import _resolve_config_path
from vcptoolbox_updater.config import load_config
from vcptoolbox_updater.tui.i18n import _


class LogViewer(Screen[None]):
    """Screen to view and tail the updater log file."""

    NAME = "log_viewer"

    CSS = """
    #log-card {
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
        self._log_file: Path | None = None
        self._file_handle = None
        self._read_bytes = 0

    def compose(self) -> ComposeResult:
        with Container(id="log-card"):
            yield Label(_("log_title"), id="title")
            yield RichLog(highlight=False, id="log")
            yield Static(_("feat_schedule"))
            yield Static(_("feat_merge"))
            yield Static(_("feat_notify"))
            yield Static("")
            yield Static(_("footer_keys"), id="footer")
            yield Button(_("back"), id="back-btn")

    def on_mount(self) -> None:
        log_widget = self.query_one("#log", RichLog)
        self._log_file = self._resolve_log_file()
        if self._log_file is None:
            log_widget.write(_("log_no_config"))
            return
        if not self._log_file.exists():
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            self._log_file.touch()

        self._file_handle = self._log_file.open("r", encoding="utf-8", errors="replace")
        self._read_bytes = self._log_file.stat().st_size
        self._tail_initial(log_widget)
        self.set_interval(1.0, self._tail_log)

    def _resolve_log_file(self) -> Path | None:
        try:
            config_path = _resolve_config_path(None)
            cfg = load_config(config_path)
            return cfg.log_file
        except Exception:
            return None

    def _tail_initial(self, log_widget: RichLog) -> None:
        if self._file_handle is None:
            return
        self._file_handle.seek(0)
        lines = self._file_handle.readlines()
        tail_lines = lines[-200:]
        for line in tail_lines:
            log_widget.write(line.rstrip("\n"))
        self._read_bytes = self._file_handle.tell()

    def _tail_log(self) -> None:
        if self._file_handle is None or self._log_file is None:
            return
        current_size = self._log_file.stat().st_size
        if current_size < self._read_bytes:
            self._file_handle.close()
            self._file_handle = self._log_file.open("r", encoding="utf-8", errors="replace")
            self._read_bytes = 0
        if current_size == self._read_bytes:
            return
        self._file_handle.seek(self._read_bytes)
        log_widget = self.query_one("#log", RichLog)
        for line in self._file_handle:
            log_widget.write(line.rstrip("\n"))
        self._read_bytes = self._file_handle.tell()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()

    def on_unmount(self) -> None:
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
