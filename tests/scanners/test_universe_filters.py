"""Fixed-fixture PASS/FAIL reproduction for every `UniverseFilter` -
no database, per `app/scanners/universe.py`'s module docstring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.db.repositories.market_data import InstrumentRow, MarketBarRow
from app.scanners.universe import (
    LiquidityFilter,
    PriceRangeFilter,
    RawFlagFilter,
    UniverseFilterInput,
)

_INSTRUMENT = InstrumentRow(
    id=1, exchange="KRX", symbol="005930", name="Samsung", currency="KRW", source="toss_openapi"
)


def _bar(close: str, volume: str, event_time: datetime) -> MarketBarRow:
    return MarketBarRow(
        instrument_id=1,
        timeframe="1d",
        event_time=event_time,
        available_at=event_time,
        ingested_at=event_time,
        revision=1,
        open_price=Decimal(close),
        high_price=Decimal(close),
        low_price=Decimal(close),
        close_price=Decimal(close),
        volume=Decimal(volume),
        currency="KRW",
        source="toss_openapi",
    )


def test_liquidity_filter_passes_when_average_turnover_meets_threshold() -> None:
    bars = [
        _bar("100", "1000", datetime(2026, 1, 1, tzinfo=UTC)),
        _bar("100", "2000", datetime(2026, 1, 2, tzinfo=UTC)),
    ]
    filter_ = LiquidityFilter(min_turnover_value=Decimal("100000"))
    result = filter_.evaluate(UniverseFilterInput(instrument=_INSTRUMENT, recent_bars=bars))
    assert result.passed is True
    assert result.observed_value == Decimal("150000")
    assert result.reason is None


def test_liquidity_filter_fails_when_average_turnover_below_threshold() -> None:
    bars = [_bar("100", "10", datetime(2026, 1, 1, tzinfo=UTC))]
    filter_ = LiquidityFilter(min_turnover_value=Decimal("100000"))
    result = filter_.evaluate(UniverseFilterInput(instrument=_INSTRUMENT, recent_bars=bars))
    assert result.passed is False
    assert result.reason is not None


def test_liquidity_filter_fails_with_no_bars() -> None:
    filter_ = LiquidityFilter(min_turnover_value=Decimal("1"))
    result = filter_.evaluate(UniverseFilterInput(instrument=_INSTRUMENT, recent_bars=[]))
    assert result.passed is False
    assert result.observed_value is None


def test_price_range_filter_passes_within_bounds() -> None:
    bars = [_bar("500", "10", datetime(2026, 1, 1, tzinfo=UTC))]
    filter_ = PriceRangeFilter(min_price=Decimal("100"), max_price=Decimal("1000"))
    result = filter_.evaluate(UniverseFilterInput(instrument=_INSTRUMENT, recent_bars=bars))
    assert result.passed is True


def test_price_range_filter_fails_above_max() -> None:
    bars = [_bar("5000", "10", datetime(2026, 1, 1, tzinfo=UTC))]
    filter_ = PriceRangeFilter(min_price=Decimal("100"), max_price=Decimal("1000"))
    result = filter_.evaluate(UniverseFilterInput(instrument=_INSTRUMENT, recent_bars=bars))
    assert result.passed is False
    assert result.reason is not None


def test_price_range_filter_fails_below_min() -> None:
    bars = [_bar("10", "10", datetime(2026, 1, 1, tzinfo=UTC))]
    filter_ = PriceRangeFilter(min_price=Decimal("100"), max_price=None)
    result = filter_.evaluate(UniverseFilterInput(instrument=_INSTRUMENT, recent_bars=bars))
    assert result.passed is False


def test_raw_flag_filter_passes_when_value_not_in_fail_values() -> None:
    instrument = InstrumentRow(
        id=1,
        exchange="KRX",
        symbol="005930",
        name=None,
        currency=None,
        source="toss_openapi",
        raw_payload={"tradingStatus": {"code": "NORMAL"}},
    )
    filter_ = RawFlagFilter(
        field_path="tradingStatus.code", fail_values=frozenset({"HALTED", "WARNING"})
    )
    result = filter_.evaluate(UniverseFilterInput(instrument=instrument, recent_bars=[]))
    assert result.passed is True
    assert result.observed_value == "NORMAL"


def test_raw_flag_filter_fails_when_value_in_fail_values() -> None:
    instrument = InstrumentRow(
        id=1,
        exchange="KRX",
        symbol="005930",
        name=None,
        currency=None,
        source="toss_openapi",
        raw_payload={"tradingStatus": {"code": "HALTED"}},
    )
    filter_ = RawFlagFilter(
        field_path="tradingStatus.code", fail_values=frozenset({"HALTED", "WARNING"})
    )
    result = filter_.evaluate(UniverseFilterInput(instrument=instrument, recent_bars=[]))
    assert result.passed is False
    assert result.reason is not None


def test_raw_flag_filter_is_unknown_not_pass_when_field_absent_by_default() -> None:
    instrument = InstrumentRow(
        id=1,
        exchange="KRX",
        symbol="005930",
        name=None,
        currency=None,
        source="toss_openapi",
        raw_payload={"unrelated": "value"},
    )
    filter_ = RawFlagFilter(field_path="tradingStatus.code", fail_values=frozenset({"HALTED"}))
    result = filter_.evaluate(UniverseFilterInput(instrument=instrument, recent_bars=[]))
    assert result.passed is False
    assert "not present" in (result.reason or "")


def test_raw_flag_filter_treat_unknown_as_pass_lets_missing_field_through() -> None:
    instrument = InstrumentRow(
        id=1,
        exchange="KRX",
        symbol="005930",
        name=None,
        currency=None,
        source="toss_openapi",
        raw_payload=None,
    )
    filter_ = RawFlagFilter(
        field_path="tradingStatus.code",
        fail_values=frozenset({"HALTED"}),
        treat_unknown_as_pass=True,
    )
    result = filter_.evaluate(UniverseFilterInput(instrument=instrument, recent_bars=[]))
    assert result.passed is True
    assert "UNKNOWN" not in (result.reason or "") or "unknown" in (result.reason or "").lower()
