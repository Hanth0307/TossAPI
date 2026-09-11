"""Structured logging setup.

Uses the standard library `logging` module with a small JSON
formatter, rather than pulling in a third-party structured-logging
dependency - Phase 00 has no need for anything more elaborate.

Usage:
    from app.core.logging import configure_logging, get_logger

    configure_logging(level="INFO", fmt="json")
    logger = get_logger(__name__)
    logger.info("order.rejected", extra={"extra_fields": {"symbol": "005930"}})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    """Renders each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        extra_fields = getattr(record, "extra_fields", None)
        if extra_fields:
            payload.update(extra_fields)

        return json.dumps(payload, ensure_ascii=False, default=str)


_CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """(Re)configure the root logger. Safe to call multiple times."""
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
