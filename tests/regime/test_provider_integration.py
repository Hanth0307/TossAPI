"""Integration test against real Postgres proving `RegimeProvider`
composes `RegimeClassifier` with an `as_of`-gated bar fetch correctly:
a correction that only becomes available after a given `as_of` never
changes that `as_of`'s regime assessment - the same future-correction-
leakage regression proven for the Scanner pipeline in
`tests/scanners/test_pipeline_integration.py`, here for Market Regime.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.repositories.market_data import InstrumentRepository, MarketBarRepository
from app.regime.classifier import RegimeClassifier, TrendState
from app.regime.provider import RegimeProvider


def _classifier() -> RegimeClassifier:
    return RegimeClassifier(
        trend_lookback_bars=1,
        trend_up_threshold=Decimal("0.05"),
        trend_down_threshold=Decimal("-0.05"),
        volatility_lookback_bars=1,
        high_volatility_threshold=Decimal("1"),
        low_volatility_threshold=Decimal("0"),
        breadth_expanding_threshold=Decimal("0.6"),
        breadth_contracting_threshold=Decimal("0.4"),
    )


def test_future_correction_leakage_regression__regime_before_correction_sees_original_value(
    db_session: Session,
) -> None:
    instruments = InstrumentRepository(db_session)
    bars = MarketBarRepository(db_session)
    instrument = instruments.get_or_create(exchange="KRX", symbol="REGIMEPIT", source="test")

    day0 = datetime(2026, 1, 1, tzinfo=UTC)
    day1 = datetime(2026, 1, 2, tzinfo=UTC)
    original_available_at = datetime(2026, 1, 2, tzinfo=UTC)
    corrected_available_at = datetime(2026, 1, 4, tzinfo=UTC)

    def row(event_time, available_at, close):
        return {
            "instrument_id": instrument.id, "timeframe": "1d", "event_time": event_time,
            "available_at": available_at, "ingested_at": available_at,
            "open_price": Decimal(close), "high_price": Decimal(close),
            "low_price": Decimal(close), "close_price": Decimal(close),
            "volume": Decimal("1000"), "currency": "KRW", "source": "test",
        }

    bars.upsert_bars([row(day0, day0, "1000")])
    # Original day1 close: flat (no trend). Later correction: sharp rally.
    bars.upsert_bars([row(day1, original_available_at, "1005")])
    bars.upsert_bars([row(day1, corrected_available_at, "1200")])

    provider = RegimeProvider(
        db_session, classifier=_classifier(), benchmark_instrument_id=instrument.id,
        timeframe="1d", lookback_days=10,
    )

    as_of_before_correction = datetime(2026, 1, 3, tzinfo=UTC)
    assessment_before = provider.get_regime_as_of(as_of=as_of_before_correction)
    assert assessment_before.trend == TrendState.SIDEWAYS


def test_future_correction_leakage_regression__regime_after_correction_sees_corrected_value(
    db_session: Session,
) -> None:
    instruments = InstrumentRepository(db_session)
    bars = MarketBarRepository(db_session)
    instrument = instruments.get_or_create(exchange="KRX", symbol="REGIMEPIT2", source="test")

    day0 = datetime(2026, 1, 1, tzinfo=UTC)
    day1 = datetime(2026, 1, 2, tzinfo=UTC)
    original_available_at = datetime(2026, 1, 2, tzinfo=UTC)
    corrected_available_at = datetime(2026, 1, 4, tzinfo=UTC)

    def row(event_time, available_at, close):
        return {
            "instrument_id": instrument.id, "timeframe": "1d", "event_time": event_time,
            "available_at": available_at, "ingested_at": available_at,
            "open_price": Decimal(close), "high_price": Decimal(close),
            "low_price": Decimal(close), "close_price": Decimal(close),
            "volume": Decimal("1000"), "currency": "KRW", "source": "test",
        }

    bars.upsert_bars([row(day0, day0, "1000")])
    bars.upsert_bars([row(day1, original_available_at, "1005")])
    bars.upsert_bars([row(day1, corrected_available_at, "1200")])

    provider = RegimeProvider(
        db_session, classifier=_classifier(), benchmark_instrument_id=instrument.id,
        timeframe="1d", lookback_days=10,
    )

    as_of_after_correction = datetime(2026, 1, 5, tzinfo=UTC)
    assessment_after = provider.get_regime_as_of(as_of=as_of_after_correction)
    assert assessment_after.trend == TrendState.UPTREND
