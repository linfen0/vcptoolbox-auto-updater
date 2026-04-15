"""Unit tests for logging utilities."""

import logging
from unittest.mock import MagicMock, patch

import structlog

from vcptoolbox_updater.utils import configure_logging, get_logger


def test_get_logger():
    logger = get_logger("test_module")
    assert logger is not None


def test_configure_logging_cli_mode():
    with patch("vcptoolbox_updater.utils.structlog.configure") as mock_configure, \
         patch("vcptoolbox_updater.utils.logging.StreamHandler") as mock_stream_handler, \
         patch("vcptoolbox_updater.utils.sys.stdout") as mock_stdout:
        mock_stdout.isatty.return_value = True
        mock_handler = MagicMock()
        mock_stream_handler.return_value = mock_handler
        configure_logging("INFO", None, service_mode=False)
        mock_configure.assert_called_once()
        args, kwargs = mock_configure.call_args
        assert isinstance(kwargs["processors"][-1], structlog.dev.ConsoleRenderer)


def test_configure_logging_service_mode_with_file():
    with patch("vcptoolbox_updater.utils.structlog.configure") as mock_configure, \
         patch("vcptoolbox_updater.utils.logging.handlers.RotatingFileHandler") as mock_rotating, \
         patch("vcptoolbox_updater.utils.logging.handlers.NTEventLogHandler") as mock_event:
        mock_rotating.return_value = MagicMock(spec=logging.Handler)
        mock_event.return_value = MagicMock(spec=logging.Handler)
        configure_logging("DEBUG", "/tmp/test.log", service_mode=True)
        mock_configure.assert_called_once()
        mock_rotating.assert_called_once_with(
            "/tmp/test.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
