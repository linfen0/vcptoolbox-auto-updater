"""TUI entry point for VCPToolBox Auto Updater."""

from __future__ import annotations

from vcptoolbox_updater.tui.app import UpdaterTuiApp


def main() -> None:
    UpdaterTuiApp().run()


if __name__ == "__main__":
    main()
