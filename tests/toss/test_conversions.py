from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.exceptions import DataValidationError
from app.toss.conversions import parse_timestamp, to_decimal


def test_to_decimal_parses_a_valid_numeric_string() -> None:
    assert to_decimal("72000", field="lastPrice") == Decimal("72000")


def test_to_decimal_raises_data_validation_error_on_garbage() -> None:
    with pytest.raises(DataValidationError, match="lastPrice"):
        to_decimal("not-a-number", field="lastPrice")


def test_parse_timestamp_parses_a_valid_offset_timestamp() -> None:
    parsed = parse_timestamp("2026-03-25T09:30:00.123+09:00", field="timestamp")
    assert parsed.tzinfo is not None
    assert parsed.year == 2026


def test_parse_timestamp_raises_data_validation_error_on_garbage() -> None:
    with pytest.raises(DataValidationError, match="timestamp"):
        parse_timestamp("not-a-timestamp", field="timestamp")


def test_parse_timestamp_rejects_naive_datetime_string() -> None:
    with pytest.raises(DataValidationError, match="timezone-aware"):
        parse_timestamp("2026-03-25T09:30:00", field="timestamp")
