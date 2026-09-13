"""Fixed-fixture PASS/FAIL reproduction for each `RegimeClassifier`
dimension (trend/volatility/breadth) - no database, per
`app/regime/classifier.py`'s module docstring.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.repositories.market_data import MarketBarRow
from app.regime.classifier import (
    BreadthState,
    RegimeClassifier,
    RegimeInput,
    TrendState,
    VolatilityLevel,
)

_AS_OF = datetime(2026, 2, 1, tzinfo=UTC)


def _bar(i: int, close: str) -> MarketBarRow:
    t = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)
    return MarketBarRow(
        instrument_id=1, timeframe="1d", event_time=t, available_at=t, ingested_at=t,
        revision=1, open_price=Decimal(close), high_price=Decimal(close),
        low_price=Decimal(close), close_price=Decimal(close), volume=Decimal("1000"),
        currency="KRW", source="test",
    )


def _classifier(**overrides: object) -> RegimeClassifier:
    defaults = dict(
        trend_lookback_bars=20,
        trend_up_threshold=Decimal("0.03"),
        trend_down_threshold=Decimal("-0.03"),
        volatility_lookback_bars=20,
        high_volatility_threshold=Decimal("0.02"),
        low_volatility_threshold=Decimal("0.001"),
        breadth_expanding_threshold=Decimal("0.6"),
        breadth_contracting_threshold=Decimal("0.4"),
    )
    defaults.update(overrides)
    return RegimeClassifier(**defaults)  # type: ignore[arg-type]


def test_trend_detects_uptrend_above_threshold() -> None:
    bars = [_bar(i, str(1000 + i * 5)) for i in range(21)]
    result = _classifier().classify(RegimeInput(bars=bars), as_of=_AS_OF)
    assert result.trend == TrendState.UPTREND
    assert result.observed_return is not None and result.observed_return > 0


def test_trend_detects_downtrend_below_threshold() -> None:
    bars = [_bar(i, str(1000 - i * 5)) for i in range(21)]
    result = _classifier().classify(RegimeInput(bars=bars), as_of=_AS_OF)
    assert result.trend == TrendState.DOWNTREND


def test_trend_is_sideways_within_thresholds() -> None:
    bars = [_bar(i, "1000") for i in range(21)]
    result = _classifier().classify(RegimeInput(bars=bars), as_of=_AS_OF)
    assert result.trend == TrendState.SIDEWAYS


def test_trend_is_unknown_with_insufficient_bars() -> None:
    bars = [_bar(i, "1000") for i in range(5)]
    result = _classifier().classify(RegimeInput(bars=bars), as_of=_AS_OF)
    assert result.trend == TrendState.UNKNOWN
    assert result.observed_return is None


def test_volatility_detects_high_volatility() -> None:
    closes = [1000, 1050, 980, 1080, 950, 1100] * 4
    bars = [_bar(i, str(c)) for i, c in enumerate(closes[:21])]
    result = _classifier().classify(RegimeInput(bars=bars), as_of=_AS_OF)
    assert result.volatility_level == VolatilityLevel.HIGH


def test_volatility_detects_low_volatility() -> None:
    bars = [_bar(i, str(1000 + i)) for i in range(21)]
    result = _classifier().classify(RegimeInput(bars=bars), as_of=_AS_OF)
    assert result.volatility_level == VolatilityLevel.LOW


def test_breadth_detects_expanding() -> None:
    bars = [_bar(i, "1000") for i in range(21)]
    result = _classifier().classify(
        RegimeInput(bars=bars, advancing_count=800, declining_count=200), as_of=_AS_OF
    )
    assert result.breadth == BreadthState.EXPANDING
    assert result.observed_breadth_ratio == Decimal("0.8")


def test_breadth_detects_contracting() -> None:
    bars = [_bar(i, "1000") for i in range(21)]
    result = _classifier().classify(
        RegimeInput(bars=bars, advancing_count=100, declining_count=900), as_of=_AS_OF
    )
    assert result.breadth == BreadthState.CONTRACTING


def test_breadth_is_unknown_without_advance_decline_counts() -> None:
    bars = [_bar(i, "1000") for i in range(21)]
    result = _classifier().classify(RegimeInput(bars=bars), as_of=_AS_OF)
    assert result.breadth == BreadthState.UNKNOWN
    assert result.observed_breadth_ratio is None


def test_reasons_are_recorded_for_every_dimension() -> None:
    bars = [_bar(i, "1000") for i in range(21)]
    result = _classifier().classify(
        RegimeInput(bars=bars, advancing_count=500, declining_count=500), as_of=_AS_OF
    )
    assert len(result.reasons) == 3


def test_classifier_never_looks_beyond_the_bars_it_is_given() -> None:
    """A classifier fed only 21 bars (no more, no less) cannot possibly
    have used a 22nd, "future" bar - this is what makes `RegimeClassifier`
    safe to compose with an as_of-gated fetch without any as_of-awareness
    of its own."""
    bars_short = [_bar(i, str(1000 + i * 10)) for i in range(21)]
    bars_long = bars_short + [_bar(21, "999999")]  # a wildly different future bar

    result_short = _classifier().classify(RegimeInput(bars=bars_short), as_of=_AS_OF)
    result_without_future = _classifier().classify(
        RegimeInput(bars=bars_long[:21]), as_of=_AS_OF
    )
    assert result_short.trend == result_without_future.trend
    assert result_short.observed_return == result_without_future.observed_return
