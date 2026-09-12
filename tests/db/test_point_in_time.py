"""Point-in-time reads: `available_at <= as_of` must never leak data
that only became available after the query's `as_of` cutoff - the
core anti-lookahead guarantee for backtesting/model training.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.repositories.market_data import InstrumentRepository, MarketBarRepository

DAY = timedelta(days=1)
BASE = datetime(2026, 3, 1, tzinfo=UTC)


def _bar(instrument_id: int, day_offset: int, available_lag_minutes: int, close: str) -> dict:
    event_time = BASE + day_offset * DAY
    available_at = event_time + timedelta(minutes=available_lag_minutes)
    return {
        "instrument_id": instrument_id,
        "timeframe": "1d",
        "event_time": event_time,
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


def test_query_as_of_before_a_bar_is_available_excludes_it(migrated_schema, db_session) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)
    # Bar for day 5, only available 10 minutes after its event_time.
    bars.upsert_bars([_bar(instrument.id, 5, 10, "100")])

    as_of_before_available = BASE + 5 * DAY + timedelta(minutes=5)
    result = bars.get_bars_as_of(
        instrument_id=instrument.id,
        timeframe="1d",
        start=BASE,
        end=BASE + 10 * DAY,
        as_of=as_of_before_available,
    )

    assert result == []


def test_query_as_of_after_a_bar_is_available_includes_it(migrated_schema, db_session) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)
    bars.upsert_bars([_bar(instrument.id, 5, 10, "100")])

    as_of_after_available = BASE + 5 * DAY + timedelta(minutes=15)
    result = bars.get_bars_as_of(
        instrument_id=instrument.id,
        timeframe="1d",
        start=BASE,
        end=BASE + 10 * DAY,
        as_of=as_of_after_available,
    )

    assert len(result) == 1
    assert result[0].close_price == Decimal("100")


def test_as_of_cutoff_never_leaks_future_bars_into_a_training_style_query(
    migrated_schema, db_session
) -> None:
    """Simulates a walk-forward training query: as training day advances,
    only bars available by that point should ever appear - never a bar
    from a later day, even though it already exists in the table.
    """
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars_repo = MarketBarRepository(db_session)
    # Ingest 10 days of bars "all at once" (as a real backfill would),
    # each available shortly after its own event_time.
    bars_repo.upsert_bars(
        [
            _bar(instrument.id, day, available_lag_minutes=10, close=str(100 + day))
            for day in range(10)
        ]
    )

    as_of = BASE + 4 * DAY + timedelta(minutes=15)  # day 4's bar is available, day 5's is not yet
    result = bars_repo.get_bars_as_of(
        instrument_id=instrument.id,
        timeframe="1d",
        start=BASE,
        end=BASE + 10 * DAY,
        as_of=as_of,
    )

    event_days = {(row.event_time - BASE).days for row in result}
    assert event_days == {0, 1, 2, 3, 4}
    assert all(row.available_at <= as_of for row in result)


def test_a_later_correction_does_not_retroactively_change_an_earlier_as_of_answer(
    migrated_schema, db_session
) -> None:
    """A bar corrected well after the fact must NOT appear (with its
    corrected value) for an as_of cutoff before the correction actually
    happened - this is the future-correction-leakage guarantee. See
    tests/db/test_point_in_time_correction.py for the full dedicated
    regression suite (the exact scenario from ADR 0009) and
    `app.db.upsert.append_revision_rows` for how it is enforced (a
    correction is a new revision row, never an in-place overwrite).
    """
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars_repo = MarketBarRepository(db_session)

    original_available_at = BASE + 1 * DAY + timedelta(minutes=10)
    bars_repo.upsert_bars([_bar(instrument.id, 1, 10, "100")])

    as_of_between_original_and_correction = original_available_at + timedelta(hours=1)
    result_before_correction = bars_repo.get_bars_as_of(
        instrument_id=instrument.id,
        timeframe="1d",
        start=BASE,
        end=BASE + 10 * DAY,
        as_of=as_of_between_original_and_correction,
    )
    assert len(result_before_correction) == 1
    assert result_before_correction[0].close_price == Decimal("100")

    # A correction arrives much later with a new available_at - appended
    # as a new revision, the original row is untouched.
    later_correction = {
        **_bar(instrument.id, 1, 10, "999"),
        "available_at": original_available_at + timedelta(days=5),
        "ingested_at": original_available_at + timedelta(days=5),
    }
    bars_repo.upsert_bars([later_correction])

    # Querying with the SAME as_of as before must still return the
    # ORIGINAL value - the correction's available_at is in the future
    # relative to this as_of, so it must not leak in.
    result_still_before_correction = bars_repo.get_bars_as_of(
        instrument_id=instrument.id,
        timeframe="1d",
        start=BASE,
        end=BASE + 10 * DAY,
        as_of=as_of_between_original_and_correction,
    )
    assert len(result_still_before_correction) == 1
    assert result_still_before_correction[0].close_price == Decimal("100")

    # An as_of after the correction's available_at sees the correction.
    result_after_correction = bars_repo.get_bars_as_of(
        instrument_id=instrument.id,
        timeframe="1d",
        start=BASE,
        end=BASE + 10 * DAY,
        as_of=original_available_at + timedelta(days=6),
    )
    assert len(result_after_correction) == 1
    assert result_after_correction[0].close_price == Decimal("999")
