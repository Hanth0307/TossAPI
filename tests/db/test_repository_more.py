"""Coverage top-up for repository paths not hit by the main
idempotency/point-in-time/resume tests: trade ticks, orderbook
snapshots, paper order status updates, and run-without-idempotency-key.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.repositories.market_data import (
    InstrumentRepository,
    OrderbookRepository,
    TradeTickRepository,
)
from app.db.repositories.orders import PaperOrderRepository
from app.db.repositories.runs import BacktestRunRepository, ModelRunRepository

NOW = datetime(2026, 3, 25, 9, 0, tzinfo=UTC)


def test_trade_tick_upsert_and_point_in_time_read(migrated_schema, db_session) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="mock"
    )
    ticks = TradeTickRepository(db_session)
    row = {
        "instrument_id": instrument.id,
        "event_time": NOW,
        "available_at": NOW,
        "ingested_at": NOW,
        "price": Decimal("72000"),
        "volume": Decimal("120"),
        "currency": "KRW",
        "source": "toss_openapi",
        "raw_payload": None,
    }
    ticks.upsert_ticks([row])
    ticks.upsert_ticks([row])  # identical re-ingest, DO NOTHING policy

    result = ticks.get_ticks_as_of(
        instrument_id=instrument.id,
        start=NOW - timedelta(hours=1),
        end=NOW + timedelta(hours=1),
        as_of=NOW,
    )
    assert len(result) == 1
    assert result[0].price == Decimal("72000")


def test_orderbook_upsert_and_latest_as_of(migrated_schema, db_session) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="mock"
    )
    orderbook = OrderbookRepository(db_session)
    orderbook.upsert_snapshots(
        [
            {
                "instrument_id": instrument.id,
                "event_time": NOW,
                "available_at": NOW,
                "ingested_at": NOW,
                "currency": "KRW",
                "asks": [{"price": "72300", "volume": "1200"}],
                "bids": [{"price": "72000", "volume": "5200"}],
                "source": "toss_openapi",
                "raw_payload": None,
            }
        ]
    )

    snapshot = orderbook.get_latest_as_of(instrument_id=instrument.id, as_of=NOW)
    assert snapshot is not None
    assert snapshot.asks[0]["price"] == "72300"


def test_paper_order_status_update_and_lookup(migrated_schema, db_session) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="mock"
    )
    orders = PaperOrderRepository(db_session)
    orders.record_submission(
        client_order_id="paper-status-1",
        instrument_id=instrument.id,
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("5"),
        limit_price=Decimal("1000"),
    )

    orders.update_status("paper-status-1", "filled")

    row = orders.get_by_client_order_id("paper-status-1")
    assert row is not None
    assert row.status == "filled"


def test_model_run_without_idempotency_key_always_creates_new(
    migrated_schema, db_session
) -> None:
    runs = ModelRunRepository(db_session)
    first_id, first_created = runs.start_run(model_name="ad-hoc")
    second_id, second_created = runs.start_run(model_name="ad-hoc")

    assert first_created is True
    assert second_created is True
    assert first_id != second_id


def test_backtest_run_without_idempotency_key_always_creates_new(
    migrated_schema, db_session
) -> None:
    runs = BacktestRunRepository(db_session)
    first_id, first_created = runs.start_backtest(
        strategy_id="STR-X",
        strategy_version="0.1.0",
        period_start=NOW - timedelta(days=1),
        period_end=NOW,
    )
    second_id, second_created = runs.start_backtest(
        strategy_id="STR-X",
        strategy_version="0.1.0",
        period_start=NOW - timedelta(days=1),
        period_end=NOW,
    )

    assert first_created is True
    assert second_created is True
    assert first_id != second_id
