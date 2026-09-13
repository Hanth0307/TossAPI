"""Fixed-fixture reproduction for `compute_features` - no database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.repositories.market_data import MarketBarRow
from app.models.features import FEATURE_NAMES, compute_features


def _bar(i: int, close: str, volume: str = "1000") -> MarketBarRow:
    t = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)
    return MarketBarRow(
        instrument_id=1, timeframe="1d", event_time=t, available_at=t, ingested_at=t,
        revision=1, open_price=Decimal(close), high_price=Decimal(close),
        low_price=Decimal(close), close_price=Decimal(close), volume=Decimal(volume),
        currency="KRW", source="test",
    )


def test_computes_every_named_feature_with_enough_history() -> None:
    bars = [_bar(i, str(1000 + i)) for i in range(21)]
    result = compute_features(bars)
    assert result.vector is not None
    assert set(result.vector.values) == set(FEATURE_NAMES)
    assert result.reason is None


def test_as_ordered_list_matches_feature_names_order() -> None:
    bars = [_bar(i, str(1000 + i)) for i in range(21)]
    result = compute_features(bars)
    assert result.vector is not None
    ordered = result.vector.as_ordered_list()
    assert len(ordered) == len(FEATURE_NAMES)
    for name, value in zip(FEATURE_NAMES, ordered, strict=True):
        assert result.vector.values[name] == value


def test_insufficient_history_returns_no_vector_not_a_partial_one() -> None:
    bars = [_bar(i, "1000") for i in range(10)]
    result = compute_features(bars)
    assert result.vector is None
    assert result.reason is not None


def test_flat_prices_yield_zero_volatility_and_zero_returns() -> None:
    bars = [_bar(i, "1000") for i in range(21)]
    result = compute_features(bars)
    assert result.vector is not None
    assert result.vector.values["return_20d"] == 0.0
    assert result.vector.values["volatility_20d"] == 0.0
    assert result.vector.values["price_vs_sma20"] == 0.0


def test_never_uses_a_bar_beyond_the_list_it_is_given() -> None:
    """21 bars vs. the same 21 bars plus one wildly different 22nd bar
    must produce identical features for the first 21 - the function
    never peeks past what it's handed."""
    bars_21 = [_bar(i, str(1000 + i)) for i in range(21)]
    bars_22 = bars_21 + [_bar(21, "999999")]

    result_21 = compute_features(bars_21)
    result_22_truncated = compute_features(bars_22[:21])
    assert result_21.vector == result_22_truncated.vector
