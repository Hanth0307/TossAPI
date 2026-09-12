"""Data quality metrics computed from real SQL over the Data Platform
tables: ingestion success rate, missing bars, ingestion latency,
duplicate counts, and staleness.

Duplicate ROWS structurally cannot accumulate in an observed-event
table (`app.db.upsert.upsert_event_rows`'s `ON CONFLICT` guarantees
one row per natural key) - so "duplicate count" here means "how many
rows in an ingestion batch matched an existing key" (i.e. would have
been a duplicate without the upsert), which an ingestor computes via
`compute_duplicate_count` and records for later reporting (see
`app.ingest`), not something read back from table row counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Table, func, select
from sqlalchemy.orm import Session

from app.db.schema import market_bars, system_events

# Convention for `system_events.severity` used by `compute_success_rate`:
# INFO = the run succeeded, WARNING = partial/degraded, ERROR = failed.
_SUCCESS_SEVERITY = "INFO"


@dataclass(frozen=True)
class MarketDataQualityReport:
    instrument_id: int
    timeframe: str
    start: datetime
    end: datetime
    expected_bar_count: int
    actual_bar_count: int
    missing_count: int
    avg_latency_seconds: float | None
    max_latency_seconds: float | None
    latest_ingested_at: datetime | None
    staleness_seconds: float | None
    is_stale: bool


def compute_market_data_quality(
    session: Session,
    *,
    instrument_id: int,
    timeframe: str,
    start: datetime,
    end: datetime,
    expected_interval_seconds: float,
    stale_after_seconds: float,
    now: datetime | None = None,
) -> MarketDataQualityReport:
    """Missing-bar count assumes bars are expected every
    `expected_interval_seconds` across `[start, end]` - accurate for a
    fixed-interval timeframe (e.g. "1m"), an over-count of "missing"
    for a calendar-gapped one (e.g. "1d", which skips weekends/
    holidays we have no trading calendar for yet - see ADR 0009).
    """
    now = now or datetime.now(UTC)

    filters = (
        market_bars.c.instrument_id == instrument_id,
        market_bars.c.timeframe == timeframe,
        market_bars.c.event_time >= start,
        market_bars.c.event_time <= end,
    )

    actual_count = session.execute(
        select(func.count()).select_from(market_bars).where(*filters)
    ).scalar_one()

    latency_seconds = func.extract("epoch", market_bars.c.ingested_at - market_bars.c.event_time)
    latency_stmt = select(
        func.avg(latency_seconds),
        func.max(latency_seconds),
        func.max(market_bars.c.ingested_at),
    ).where(*filters)
    avg_latency, max_latency, latest_ingested_at = session.execute(latency_stmt).one()

    span_seconds = (end - start).total_seconds()
    expected_count = (
        int(span_seconds // expected_interval_seconds) + 1
        if expected_interval_seconds > 0
        else 0
    )
    missing_count = max(expected_count - actual_count, 0)

    staleness_seconds = (
        (now - latest_ingested_at).total_seconds() if latest_ingested_at is not None else None
    )
    is_stale = staleness_seconds is None or staleness_seconds > stale_after_seconds

    return MarketDataQualityReport(
        instrument_id=instrument_id,
        timeframe=timeframe,
        start=start,
        end=end,
        expected_bar_count=expected_count,
        actual_bar_count=actual_count,
        missing_count=missing_count,
        avg_latency_seconds=float(avg_latency) if avg_latency is not None else None,
        max_latency_seconds=float(max_latency) if max_latency is not None else None,
        latest_ingested_at=latest_ingested_at,
        staleness_seconds=staleness_seconds,
        is_stale=is_stale,
    )


def compute_duplicate_count(*, attempted: int, rows_before: int, rows_after: int) -> int:
    """How many of `attempted` upserted rows matched an existing natural
    key (i.e. would have been duplicates without the upsert)."""
    new_rows = rows_after - rows_before
    return max(attempted - new_rows, 0)


def compute_success_rate(
    session: Session, *, event_type: str, source: str, since: datetime
) -> float | None:
    """Fraction of `system_events` rows for `(event_type, source)` since
    `since` with severity `INFO` (success). `None` if there are no
    matching events at all (as opposed to `0.0`, which means events
    exist and all failed).
    """
    stmt = (
        select(system_events.c.severity, func.count())
        .where(
            system_events.c.event_type == event_type,
            system_events.c.source == source,
            system_events.c.occurred_at >= since,
        )
        .group_by(system_events.c.severity)
    )
    counts: dict[str, int] = {severity: count for severity, count in session.execute(stmt)}
    total = sum(counts.values())
    if total == 0:
        return None
    return counts.get(_SUCCESS_SEVERITY, 0) / total


def compute_staleness_seconds(
    session: Session, table: Table, *, filters: tuple, now: datetime | None = None
) -> float | None:
    """Generic staleness check: seconds since `MAX(ingested_at)` for any
    observed-event table, given a tuple of SQLAlchemy filter clauses.
    """
    now = now or datetime.now(UTC)
    latest = session.execute(
        select(func.max(table.c.ingested_at)).where(*filters)
    ).scalar_one_or_none()
    if latest is None:
        return None
    return (now - latest).total_seconds()
