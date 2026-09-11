from __future__ import annotations

import json
import logging

from app.core.logging import JsonFormatter, configure_logging, get_logger


def test_json_formatter_produces_valid_json_with_expected_keys() -> None:
    logger = logging.getLogger("test.json.formatter")
    record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=0,
        msg="order.rejected",
        args=(),
        exc_info=None,
    )
    record.extra_fields = {"symbol": "005930", "reason": "risk_limit"}

    output = JsonFormatter().format(record)
    payload = json.loads(output)

    assert payload["message"] == "order.rejected"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.json.formatter"
    assert payload["symbol"] == "005930"
    assert payload["reason"] == "risk_limit"
    assert "timestamp" in payload


def test_configure_logging_sets_level_and_single_handler() -> None:
    configure_logging(level="DEBUG", fmt="json")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_get_logger_returns_named_logger() -> None:
    logger = get_logger("app.core.test")
    assert logger.name == "app.core.test"
