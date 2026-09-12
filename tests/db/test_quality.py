from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.quality import (
    compute_duplicate_count,
    compute_market_data_quality,
    compute_success_rate,
)
from app.db.repositories.market_data import InstrumentRepository, MarketBarRepository
from app.db.repositories.system_events import SystemEventRepository

NOW = datetime(2026, 3, 25, 9, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def test_market_data_quality_reports_missing_bars_and_latency(migrated_schema, db_session) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)

    start = NOW - 5 * DAY
    end = NOW
    # Only ingest 3 of the 6 expected daily bars, each with a 1-hour latency.
    rows = []
    for offset in (0, 1, 2):
        event_time = start + offset * DAY
        available_at = event_time + timedelta(hours=1)
        rows.append(
            {
                "instrument_id": instrument.id,
                "timeframe": "1d",
                "event_time": event_time,
                "available_at": available_at,
                "ingested_at": available_at,
                "open_price": Decimal("100"),
                "high_price": Decimal("110"),
                "low_price": Decimal("95"),
                "close_price": Decimal("105"),
                "volume": Decimal("1000"),
                "currency": "KRW",
                "source": "toss_openapi",
            }
        )
    bars.upsert_bars(rows)

    report = compute_market_data_quality(
        db_session,
        instrument_id=instrument.id,
        timeframe="1d",
        start=start,
        end=end,
        expected_interval_seconds=DAY.total_seconds(),
        stale_after_seconds=3600,
        now=NOW,
    )

    assert report.actual_bar_count == 3
    assert report.expected_bar_count == 6
    assert report.missing_count == 3
    assert report.avg_latency_seconds == 3600.0
    assert report.max_latency_seconds == 3600.0


def test_market_data_quality_marks_stale_when_no_recent_ingestion(
    migrated_schema, db_session
) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)
    old_event_time = NOW - 10 * DAY
    bars.upsert_bars(
        [
            {
                "instrument_id": instrument.id,
                "timeframe": "1d",
                "event_time": old_event_time,
                "available_at": old_event_time,
                "ingested_at": old_event_time,
                "open_price": Decimal("100"),
                "high_price": Decimal("110"),
                "low_price": Decimal("95"),
                "close_price": Decimal("105"),
                "volume": Decimal("1000"),
                "currency": "KRW",
                "source": "toss_openapi",
            }
        ]
    )

    report = compute_market_data_quality(
        db_session,
        instrument_id=instrument.id,
        timeframe="1d",
        start=old_event_time - DAY,
        end=NOW,
        expected_interval_seconds=DAY.total_seconds(),
        stale_after_seconds=3600,
        now=NOW,
    )

    assert report.is_stale is True
    assert report.staleness_seconds is not None
    assert report.staleness_seconds > 3600


def test_market_data_quality_reports_no_staleness_data_when_nothing_ingested(
    migrated_schema, db_session
) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="999999", source="toss_openapi"
    )
    report = compute_market_data_quality(
        db_session,
        instrument_id=instrument.id,
        timeframe="1d",
        start=NOW - 5 * DAY,
        end=NOW,
        expected_interval_seconds=DAY.total_seconds(),
        stale_after_seconds=3600,
        now=NOW,
    )
    assert report.actual_bar_count == 0
    assert report.latest_ingested_at is None
    assert report.is_stale is True  # no data at all counts as stale


def test_compute_duplicate_count() -> None:
    # 5 rows attempted, only 2 new rows landed -> 3 were duplicates.
    assert compute_duplicate_count(attempted=5, rows_before=10, rows_after=12) == 3
    assert compute_duplicate_count(attempted=5, rows_before=10, rows_after=15) == 0


def test_compute_success_rate_from_system_events(migrated_schema, db_session) -> None:
    events = SystemEventRepository(db_session)
    since = NOW - timedelta(hours=1)
    events.log_event(
        event_type="ingestion_run",
        source="market_data",
        severity="INFO",
        message="ok",
        occurred_at=NOW,
    )
    events.log_event(
        event_type="ingestion_run",
        source="market_data",
        severity="INFO",
        message="ok",
        occurred_at=NOW,
    )
    events.log_event(
        event_type="ingestion_run",
        source="market_data",
        severity="ERROR",
        message="failed",
        occurred_at=NOW,
    )

    rate = compute_success_rate(
        db_session, event_type="ingestion_run", source="market_data", since=since
    )
    assert rate == 2 / 3


def test_compute_success_rate_returns_none_when_no_events(migrated_schema, db_session) -> None:
    rate = compute_success_rate(
        db_session, event_type="nonexistent", source="nothing", since=NOW - timedelta(hours=1)
    )
    assert rate is None
