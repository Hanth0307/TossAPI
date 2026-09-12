"""Re-ingesting the same event twice must never create a duplicate row."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.db.repositories.market_data import InstrumentRepository, MarketBarRepository
from app.db.repositories.orders import PaperOrderRepository
from app.db.repositories.runs import ModelRunRepository
from app.db.repositories.system_events import SystemEventRepository
from app.db.schema import market_bars, model_runs, paper_orders, system_events

EVENT_TIME = datetime(2026, 3, 25, 0, 0, tzinfo=UTC)
AVAILABLE_AT = datetime(2026, 3, 25, 0, 5, tzinfo=UTC)


def _bar_row(instrument_id: int, available_at: datetime, close: str) -> dict:
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


def test_reingesting_the_same_market_bar_does_not_duplicate(migrated_schema, db_session) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)

    bars.upsert_bars([_bar_row(instrument.id, AVAILABLE_AT, "105")])
    bars.upsert_bars([_bar_row(instrument.id, AVAILABLE_AT, "105")])  # identical re-ingest

    count = db_session.execute(
        select(func.count())
        .select_from(market_bars)
        .where(market_bars.c.instrument_id == instrument.id)
    ).scalar_one()
    assert count == 1


def test_reingesting_a_corrected_market_bar_updates_in_place_and_preserves_available_at(
    migrated_schema, db_session
) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(db_session)

    bars.upsert_bars([_bar_row(instrument.id, AVAILABLE_AT, "105")])
    later_available_at = AVAILABLE_AT.replace(hour=1)
    bars.upsert_bars([_bar_row(instrument.id, later_available_at, "106")])  # corrected close

    rows = db_session.execute(
        select(market_bars).where(market_bars.c.instrument_id == instrument.id)
    ).mappings().all()

    assert len(rows) == 1
    assert rows[0]["close_price"] == 106
    assert rows[0]["available_at"] == AVAILABLE_AT  # first-seen time preserved, not overwritten


def test_reingesting_the_same_paper_order_client_id_does_not_duplicate(
    migrated_schema, db_session
) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    orders = PaperOrderRepository(db_session)

    first_id, first_created = orders.record_submission(
        client_order_id="paper-order-001",
        instrument_id=instrument.id,
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("10"),
        limit_price=Decimal("70000"),
    )
    second_id, second_created = orders.record_submission(
        client_order_id="paper-order-001",
        instrument_id=instrument.id,
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("10"),
        limit_price=Decimal("70000"),
    )

    assert first_created is True
    assert second_created is False
    assert first_id == second_id

    count = db_session.execute(
        select(func.count())
        .select_from(paper_orders)
        .where(paper_orders.c.client_order_id == "paper-order-001")
    ).scalar_one()
    assert count == 1


def test_reingesting_the_same_model_run_idempotency_key_resumes_instead_of_duplicating(
    migrated_schema, db_session
) -> None:
    runs = ModelRunRepository(db_session)

    first_id, first_created = runs.start_run(
        model_name="scanner-v1", idempotency_key="daily-scan-2026-03-25"
    )
    second_id, second_created = runs.start_run(
        model_name="scanner-v1", idempotency_key="daily-scan-2026-03-25"
    )

    assert first_created is True
    assert second_created is False
    assert first_id == second_id

    count = db_session.execute(
        select(func.count())
        .select_from(model_runs)
        .where(model_runs.c.idempotency_key == "daily-scan-2026-03-25")
    ).scalar_one()
    assert count == 1


def test_reingesting_the_same_system_event_dedup_key_does_not_duplicate(
    migrated_schema, db_session
) -> None:
    events = SystemEventRepository(db_session)

    events.log_event(
        event_type="ingestion_run",
        source="market_data",
        severity="INFO",
        message="ok",
        dedup_key="market_data-2026-03-25",
    )
    events.log_event(
        event_type="ingestion_run",
        source="market_data",
        severity="INFO",
        message="ok (retry)",
        dedup_key="market_data-2026-03-25",
    )

    count = db_session.execute(
        select(func.count())
        .select_from(system_events)
        .where(system_events.c.dedup_key == "market_data-2026-03-25")
    ).scalar_one()
    assert count == 1


def test_system_events_without_a_dedup_key_are_never_deduplicated(
    migrated_schema, db_session
) -> None:
    events = SystemEventRepository(db_session)

    events.log_event(event_type="heartbeat", source="scheduler", severity="INFO", message="tick")
    events.log_event(event_type="heartbeat", source="scheduler", severity="INFO", message="tick")

    count = db_session.execute(
        select(func.count())
        .select_from(system_events)
        .where(system_events.c.event_type == "heartbeat")
    ).scalar_one()
    assert count == 2
