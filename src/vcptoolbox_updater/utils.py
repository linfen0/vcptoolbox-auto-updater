"""Logging and utility helpers."""

from __future__ import annotations

import logging
import logging.handlers
import sys

import structlog


def configure_logging(level: str, log_file: str | None, service_mode: bool = False) -> None:
    """Configure structured logging for file and/or EventLog output."""
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if service_mode:
        handlers: list[logging.Handler] = []
        if log_file:
            handlers.append(logging.handlers.RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
            ))
        try:
            import win32evtlogutil
            event_handler = logging.handlers.NTEventLogHandler("VCPToolBoxAutoUpdater")
            handlers.append(event_handler)
        except Exception:
            pass
    else:
        handlers = [logging.StreamHandler(sys.stdout)]
        if log_file:
            handlers.append(logging.handlers.RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
            ))

    if sys.stdout.isatty() and not service_mode:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, level))
    fmt = "%(message)s"
    for h in handlers:
        h.setFormatter(logging.Formatter(fmt))
        root.addHandler(h)


def get_logger(name: str = __name__):
    return structlog.get_logger(name)