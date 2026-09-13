"""Fixed-fixture reproduction for `compute_forward_return_label` - no
database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.repositories.market_data import MarketBarRow
from app.models.labels import LabelDefinition, compute_forward_return_label


def _bar(i: int, close: str) -> MarketBarRow:
    t = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)
    return MarketBarRow(
        instrument_id=1, timeframe="1d", event_time=t, available_at=t, ingested_at=t,
        revision=1, open_price=Decimal(close), high_price=Decimal(close),
        low_price=Decimal(close), close_price=Decimal(close), volume=Decimal("1000"),
        currency="KRW", source="test",
    )


_DEFINITION = LabelDefinition(
    horizon_days=5, return_threshold=Decimal("0"), version="fwd_return_5d_v1"
)


def test_positive_forward_return_labels_one() -> None:
    bars = [_bar(i, str(1000 + i * 3)) for i in range(6)]
    result = compute_forward_return_label(bars, definition=_DEFINITION)
    assert result.label == 1
    assert result.forward_return == Decimal("0.015")
    assert result.reason is None


def test_negative_forward_return_labels_zero() -> None:
    bars = [_bar(i, str(1000 - i * 3)) for i in range(6)]
    result = compute_forward_return_label(bars, definition=_DEFINITION)
    assert result.label == 0
    assert result.forward_return is not None and result.forward_return < 0


def test_return_exactly_at_threshold_labels_zero() -> None:
    """`label = 1` only when the return is strictly greater than the
    threshold - a flat/zero return at threshold=0 is not "up"."""
    bars = [_bar(i, "1000") for i in range(6)]
    result = compute_forward_return_label(bars, definition=_DEFINITION)
    assert result.label == 0
    assert result.forward_return == Decimal("0")


def test_insufficient_bars_returns_no_label() -> None:
    bars = [_bar(i, "1000") for i in range(3)]
    result = compute_forward_return_label(bars, definition=_DEFINITION)
    assert result.label is None
    assert result.forward_return is None
    assert result.reason is not None


def test_zero_entry_price_returns_no_label() -> None:
    bars = [_bar(i, "0") for i in range(6)]
    result = compute_forward_return_label(bars, definition=_DEFINITION)
    assert result.label is None
    assert "zero" in (result.reason or "")


def test_excess_return_threshold_requires_beating_the_threshold() -> None:
    definition = LabelDefinition(
        horizon_days=5, return_threshold=Decimal("0.02"), version="excess_return_5d_v1"
    )
    bars = [_bar(i, str(1000 + i * 3)) for i in range(6)]  # 1.5% return
    result = compute_forward_return_label(bars, definition=definition)
    assert result.label == 0  # 1.5% < 2% threshold
