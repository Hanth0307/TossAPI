"""Integration tests against a real Postgres (see `tests/scanners/
conftest.py`) proving the two properties the phase requires that a
fixture-only test cannot: that `available_at` after the pipeline's
`as_of` never influences a scan result (the "future correction
leakage" regression, mirroring
`tests/db/test_point_in_time_correction.py`), and that persisting scan
results under two different `strategy_version`s produces distinct,
non-overwritten `model_runs`/`signals` rows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.repositories.market_data import InstrumentRepository, MarketBarRepository
from app.db.schema import model_runs, signals
from app.scanners.candidate import Candidate
from app.scanners.persistence import persist_scan_results
from app.scanners.pipeline import PipelineConfig, ScannerPipeline
from app.scanners.universe import LiquidityFilter


def test_future_correction_leakage_regression__scan_before_correction_sees_original_value(
    db_session: Session,
) -> None:
    instruments = InstrumentRepository(db_session)
    bars = MarketBarRepository(db_session)
    instrument = instruments.get_or_create(exchange="KRX", symbol="SCANPIT", source="test")

    event_time = datetime(2026, 1, 1, tzinfo=UTC)
    original_available_at = datetime(2026, 1, 2, tzinfo=UTC)
    corrected_available_at = datetime(2026, 1, 4, tzinfo=UTC)

    def _bar_row(*, available_at: datetime, volume: str) -> dict[str, object]:
        return {
            "instrument_id": instrument.id,
            "timeframe": "1d",
            "event_time": event_time,
            "available_at": available_at,
            "ingested_at": available_at,
            "open_price": Decimal("100"),
            "high_price": Decimal("100"),
            "low_price": Decimal("100"),
            "close_price": Decimal("100"),
            "volume": Decimal(volume),
            "currency": "KRW",
            "source": "test",
        }

    # Original observation: low volume - fails the liquidity threshold below.
    bars.upsert_bars([_bar_row(available_at=original_available_at, volume="10")])
    # A later correction reveals much higher volume - would pass the same
    # threshold, but only once it becomes available.
    bars.upsert_bars([_bar_row(available_at=corrected_available_at, volume="100000")])

    config = PipelineConfig(
        timeframe="1d",
        lookback_days=10,
        news_lookback_days=10,
        disclosure_lookback_days=10,
        exchange="KRX",
    )
    liquidity_filter = LiquidityFilter(min_turnover_value=Decimal("500000"))
    pipeline = ScannerPipeline(
        db_session,
        config=config,
        universe_filters=[liquidity_filter],
        event_scanners=[],
        strategy_rule_set=None,
        data_source="test",
    )

    as_of_before_correction = datetime(2026, 1, 3, tzinfo=UTC)
    candidates_before = pipeline.scan(as_of=as_of_before_correction)
    candidate_before = next(c for c in candidates_before if c.symbol == "SCANPIT")
    assert candidate_before.passed_universe is False
    assert candidate_before.universe_results[0].observed_value == Decimal("1000")


def test_future_correction_leakage_regression__scan_after_correction_sees_corrected_value(
    db_session: Session,
) -> None:
    instruments = InstrumentRepository(db_session)
    bars = MarketBarRepository(db_session)
    instrument = instruments.get_or_create(exchange="KRX", symbol="SCANPIT2", source="test")

    event_time = datetime(2026, 1, 1, tzinfo=UTC)
    original_available_at = datetime(2026, 1, 2, tzinfo=UTC)
    corrected_available_at = datetime(2026, 1, 4, tzinfo=UTC)

    def _bar_row(*, available_at: datetime, volume: str) -> dict[str, object]:
        return {
            "instrument_id": instrument.id,
            "timeframe": "1d",
            "event_time": event_time,
            "available_at": available_at,
            "ingested_at": available_at,
            "open_price": Decimal("100"),
            "high_price": Decimal("100"),
            "low_price": Decimal("100"),
            "close_price": Decimal("100"),
            "volume": Decimal(volume),
            "currency": "KRW",
            "source": "test",
        }

    bars.upsert_bars([_bar_row(available_at=original_available_at, volume="10")])
    bars.upsert_bars([_bar_row(available_at=corrected_available_at, volume="100000")])

    config = PipelineConfig(
        timeframe="1d",
        lookback_days=10,
        news_lookback_days=10,
        disclosure_lookback_days=10,
        exchange="KRX",
    )
    liquidity_filter = LiquidityFilter(min_turnover_value=Decimal("500000"))
    pipeline = ScannerPipeline(
        db_session,
        config=config,
        universe_filters=[liquidity_filter],
        event_scanners=[],
        strategy_rule_set=None,
        data_source="test",
    )

    as_of_after_correction = datetime(2026, 1, 5, tzinfo=UTC)
    candidates_after = pipeline.scan(as_of=as_of_after_correction)
    candidate_after = next(c for c in candidates_after if c.symbol == "SCANPIT2")
    assert candidate_after.passed_universe is True
    assert candidate_after.universe_results[0].observed_value == Decimal("10000000")


def test_strategy_version_segregation__distinct_model_runs_and_signals(
    db_session: Session,
) -> None:
    instruments = InstrumentRepository(db_session)
    instrument = instruments.get_or_create(exchange="KRX", symbol="SEGTEST", source="test")
    as_of = datetime(2026, 1, 1, tzinfo=UTC)
    candidate = Candidate(
        instrument_id=instrument.id,
        symbol="SEGTEST",
        exchange="KRX",
        as_of=as_of,
        data_source="test",
        universe_results=[],
        event_detections=[],
        strategy_result=None,
        qualified=True,
        generated_at=as_of,
    )

    persisted_v1 = persist_scan_results(
        db_session,
        [candidate],
        model_name="test_model",
        strategy_id="STR-SEG-001",
        strategy_version="1.0.0",
        as_of=as_of,
    )
    persisted_v2 = persist_scan_results(
        db_session,
        [candidate],
        model_name="test_model",
        strategy_id="STR-SEG-001",
        strategy_version="2.0.0",
        as_of=as_of,
    )

    assert persisted_v1 == 1
    assert persisted_v2 == 1

    runs = (
        db_session.execute(
            select(model_runs).where(model_runs.c.strategy_id == "STR-SEG-001")
        )
        .mappings()
        .all()
    )
    assert len(runs) == 2
    versions = {row["strategy_version"] for row in runs}
    assert versions == {"1.0.0", "2.0.0"}

    run_ids = [row["id"] for row in runs]
    signal_rows = (
        db_session.execute(select(signals).where(signals.c.model_run_id.in_(run_ids)))
        .mappings()
        .all()
    )
    assert len(signal_rows) == 2
    assert {row["model_run_id"] for row in signal_rows} == set(run_ids)
