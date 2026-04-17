"""Tests for TUI i18n module."""

from vcptoolbox_updater.tui.i18n import _


def test_i18n_returns_chinese():
    assert _("menu_title").startswith("📋")
    assert "自动更新器" in _("menu_title")
    assert _("feat_service").startswith("🖥️")
    assert "开机自启" in _("feat_service")


def test_i18n_format_placeholder():
    assert "installed" in _("service_result", action="Install", output="installed")
    assert "不存在" in _("log_not_found", path="/tmp/test.log")
