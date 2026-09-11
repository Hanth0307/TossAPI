"""Shared parsing helpers: Toss's string-typed numbers and timestamps
converted to `Decimal` / timezone-aware `datetime` per house rules
(never `float` for money/quantity; never a naive datetime).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.core.exceptions import DataValidationError


def to_decimal(value: str, *, field: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise DataValidationError(f"Could not parse {field!r} as a decimal: {value!r}") from exc


def parse_timestamp(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise DataValidationError(f"Could not parse {field!r} as a timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise DataValidationError(f"{field!r} timestamp is not timezone-aware: {value!r}")
    return parsed
