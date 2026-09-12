"""Future-correction-leakage regression test.

This file exists to lock in one guarantee: **a correction to an
already-ingested observed event must never become visible to a
point-in-time query whose `as_of` predates that correction.** That is
exactly what a plain "UPSERT, keep the original available_at"
strategy gets wrong (see ADR 0009's "why plain UPSERT is dangerous"
section) - a corrected value would silently leak backward in time into
any backtest/training query run against an `as_of` before the
correction ever happened. `app.db.upsert.append_revision_rows` fixes
this by inserting the correction as a new, separate revision row
rather than overwriting the original.

The scenario below is the exact one from ADR 0009 / the Phase 03
completion review:

    Original:   value=100, available_at=2026-09-01
    Correction: value=105, available_at=2026-09-03

    as_of=2026-09-02  -> must return 100 (the correction did not exist yet)
    as_of=2026-09-04  -> must return 105 (the correction is now known)

Runs against a real local PostgreSQL (see tests/db/conftest.py) -
`ON CONFLICT`/`DISTINCT ON` semantics here are genuinely
Postgres-specific.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.db.repositories.market_data import InstrumentRepository, MarketBarRepository
from app.db.repositories.news import NewsRepository
from app.db.schema import market_bars, news_events

EVENT_TIME = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
ORIGINAL_AVAILABLE_AT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
CORRECTION_AVAILABLE_AT = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
AS_OF_BETWEEN = datetime(2026, 9, 2, 0, 0, tzinfo=UTC)
AS_OF_AFTER = datetime(2026, 9, 4, 0, 0, tzinfo=UTC)


def _bar(instrument_id: int, *, available_at: datetime, close: str) -> dict:
    return {
        "instrument_id": instrument_id,
        "timeframe": "1d",
        "event_time": EVENT_TIME,
        "available_at": available_at,
        "ingested_at": available_at,
        "open_price": Decimal("100"),
        "high_price": Decimal("110"),
        "low_price": Decimal("95"),
        "close_price": Decimal(close),
        "volume": Decimal("1000"),
        "currency": "KRW",
        "source": "toss_openapi",
    }


def _bars_as_of(repo: MarketBarRepository, instrument_id: int, as_of: datetime) -> list:
    return repo.get_bars_as_of(
        instrument_id=instrument_id,
        timeframe="1d",
        start=EVENT_TIME - timedelta(days=1),
        end=EVENT_TIME + timedelta(days=1),
        as_of=as_of,
    )


def test_future_correction_leakage_regression__initial_event_is_stored(
    migrated_schema, db_session
) -> None:
    """Step 1: the original event is stored as revision 1."""
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)

    bars.upsert_bars([_bar(instrument.id, available_at=ORIGINAL_AVAILABLE_AT, close="100")])

    row = db_session.execute(
        select(market_bars).where(market_bars.c.instrument_id == instrument.id)
    ).mappings().one()
    assert row["close_price"] == 100
    assert row["revision"] == 1


def test_future_correction_leakage_regression__correction_is_stored_as_a_new_revision(
    migrated_schema, db_session
) -> None:
    """Step 2: a correction with a later available_at is APPENDED, not
    an overwrite of the original row.
    """
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)

    bars.upsert_bars([_bar(instrument.id, available_at=ORIGINAL_AVAILABLE_AT, close="100")])
    bars.upsert_bars([_bar(instrument.id, available_at=CORRECTION_AVAILABLE_AT, close="105")])

    rows = db_session.execute(
        select(market_bars)
        .where(market_bars.c.instrument_id == instrument.id)
        .order_by(market_bars.c.revision)
    ).mappings().all()

    assert [r["revision"] for r in rows] == [1, 2]
    assert [r["close_price"] for r in rows] == [100, 105]
    assert [r["available_at"] for r in rows] == [ORIGINAL_AVAILABLE_AT, CORRECTION_AVAILABLE_AT]


def test_future_correction_leakage_regression__as_of_between_original_and_correction_sees_original(
    migrated_schema, db_session
) -> None:
    """Step 3: as_of=2026-09-02 (between the original and the
    correction) MUST return 100 - the correction was not available yet.
    This is the core anti-leakage assertion.
    """
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)
    bars.upsert_bars([_bar(instrument.id, available_at=ORIGINAL_AVAILABLE_AT, close="100")])
    bars.upsert_bars([_bar(instrument.id, available_at=CORRECTION_AVAILABLE_AT, close="105")])

    result = _bars_as_of(bars, instrument.id, AS_OF_BETWEEN)

    assert len(result) == 1
    assert result[0].close_price == Decimal("100")


def test_future_correction_leakage_regression__as_of_after_correction_sees_correction(
    migrated_schema, db_session
) -> None:
    """Step 4: as_of=2026-09-04 (after the correction) MUST return 105."""
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)
    bars.upsert_bars([_bar(instrument.id, available_at=ORIGINAL_AVAILABLE_AT, close="100")])
    bars.upsert_bars([_bar(instrument.id, available_at=CORRECTION_AVAILABLE_AT, close="105")])

    result = _bars_as_of(bars, instrument.id, AS_OF_AFTER)

    assert len(result) == 1
    assert result[0].close_price == Decimal("105")


def test_future_correction_leakage_regression__current_state_query_also_sees_correction(
    migrated_schema, db_session
) -> None:
    """Step 5: a "latest state" read - i.e. the same as_of-required
    method called with as_of=now() - also returns the correction. There
    is no separate unguarded "get current" method (as_of stays
    mandatory - see app.db.repositories module docstring); "current" is
    simply as_of=now().
    """
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)
    bars.upsert_bars([_bar(instrument.id, available_at=ORIGINAL_AVAILABLE_AT, close="100")])
    bars.upsert_bars([_bar(instrument.id, available_at=CORRECTION_AVAILABLE_AT, close="105")])

    result = _bars_as_of(bars, instrument.id, datetime.now(UTC))

    assert len(result) == 1
    assert result[0].close_price == Decimal("105")


def test_future_correction_leakage_regression__resubmitting_the_same_correction_is_idempotent(
    migrated_schema, db_session
) -> None:
    """Step 6: re-ingesting the EXACT same correction (identical
    available_at) again must not create a second revision row.
    """
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)
    bars.upsert_bars([_bar(instrument.id, available_at=ORIGINAL_AVAILABLE_AT, close="100")])
    bars.upsert_bars([_bar(instrument.id, available_at=CORRECTION_AVAILABLE_AT, close="105")])

    bars.upsert_bars([_bar(instrument.id, available_at=CORRECTION_AVAILABLE_AT, close="105")])
    bars.upsert_bars([_bar(instrument.id, available_at=CORRECTION_AVAILABLE_AT, close="105")])

    count = db_session.execute(
        select(func.count())
        .select_from(market_bars)
        .where(market_bars.c.instrument_id == instrument.id)
    ).scalar_one()
    assert count == 2  # original + the one correction, however many times it was resubmitted


def test_future_correction_leakage_regression__correction_never_changes_a_past_as_of_result(
    migrated_schema, db_session
) -> None:
    """Step 7: the defining regression check. Read as_of=2026-09-02
    BEFORE the correction exists at all, then ingest the correction,
    then read as_of=2026-09-02 again - the two answers must be
    byte-for-byte identical. If a correction could ever change a
    result for an as_of that already passed, every previously-run
    backtest/training result computed at that as_of would silently
    become unreproducible - the exact failure mode this design exists
    to prevent.
    """
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)
    bars.upsert_bars([_bar(instrument.id, available_at=ORIGINAL_AVAILABLE_AT, close="100")])

    result_before_correction_exists = _bars_as_of(bars, instrument.id, AS_OF_BETWEEN)
    assert len(result_before_correction_exists) == 1
    assert result_before_correction_exists[0].close_price == Decimal("100")

    # The correction is ingested well after that read was taken.
    bars.upsert_bars([_bar(instrument.id, available_at=CORRECTION_AVAILABLE_AT, close="105")])

    result_replayed_at_same_as_of = _bars_as_of(bars, instrument.id, AS_OF_BETWEEN)

    assert result_replayed_at_same_as_of == result_before_correction_exists


def test_future_correction_leakage_regression__applies_to_news_events_too(
    migrated_schema, db_session
) -> None:
    """The same mechanism (not just market_bars) protects news_events -
    a corrected headline must not leak into an as_of before the
    correction.
    """
    news = NewsRepository(db_session)
    original = {
        "source": "mock",
        "external_id": "article-1",
        "event_time": EVENT_TIME,
        "available_at": ORIGINAL_AVAILABLE_AT,
        "ingested_at": ORIGINAL_AVAILABLE_AT,
        "headline": "Preliminary: company reports strong results",
        "body": None,
        "related_symbols": ["005930"],
        "raw_payload": None,
    }
    correction = {
        **original,
        "available_at": CORRECTION_AVAILABLE_AT,
        "ingested_at": CORRECTION_AVAILABLE_AT,
        "headline": "CORRECTED: company reports results in line with expectations",
    }
    news.upsert_news([original])
    news.upsert_news([correction])

    before = news.get_news_as_of(
        start=EVENT_TIME - timedelta(days=1),
        end=EVENT_TIME + timedelta(days=1),
        as_of=AS_OF_BETWEEN,
    )
    after = news.get_news_as_of(
        start=EVENT_TIME - timedelta(days=1),
        end=EVENT_TIME + timedelta(days=1),
        as_of=AS_OF_AFTER,
    )

    assert len(before) == 1
    assert before[0].headline == "Preliminary: company reports strong results"
    assert len(after) == 1
    assert after[0].headline == "CORRECTED: company reports results in line with expectations"

    count = db_session.execute(
        select(func.count())
        .select_from(news_events)
        .where(news_events.c.external_id == "article-1")
    ).scalar_one()
    assert count == 2
