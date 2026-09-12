"""Smoke tests for the repositories not already exercised by
test_idempotency.py / test_point_in_time.py: news, disclosure,
strategy_registry, signals, backtest_runs, broker_orders, positions,
account_snapshots.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.repositories.account import AccountSnapshotRepository
from app.db.repositories.disclosure import DisclosureRepository
from app.db.repositories.market_data import InstrumentRepository
from app.db.repositories.news import NewsRepository
from app.db.repositories.orders import BrokerOrderRepository
from app.db.repositories.positions import PositionRepository
from app.db.repositories.runs import BacktestRunRepository, ModelRunRepository
from app.db.repositories.signals import SignalRepository
from app.db.repositories.strategy import StrategyRegistryRepository

NOW = datetime(2026, 3, 25, 9, 0, tzinfo=UTC)


def test_news_upsert_and_point_in_time_read(migrated_schema, db_session) -> None:
    news = NewsRepository(db_session)
    news.upsert_news(
        [
            {
                "source": "mock",
                "external_id": "article-1",
                "event_time": NOW,
                "available_at": NOW,
                "ingested_at": NOW,
                "headline": "Sample headline",
                "body": None,
                "related_symbols": ["005930"],
                "raw_payload": None,
            }
        ]
    )
    # Re-ingest identical article - must not duplicate.
    news.upsert_news(
        [
            {
                "source": "mock",
                "external_id": "article-1",
                "event_time": NOW,
                "available_at": NOW,
                "ingested_at": NOW,
                "headline": "Sample headline",
                "body": None,
                "related_symbols": ["005930"],
                "raw_payload": None,
            }
        ]
    )

    results = news.get_news_as_of(
        start=NOW - timedelta(days=1), end=NOW + timedelta(days=1), as_of=NOW, symbol="005930"
    )
    assert len(results) == 1
    assert results[0].headline == "Sample headline"


def test_disclosure_upsert_and_point_in_time_read(migrated_schema, db_session) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="mock"
    )
    disclosures = DisclosureRepository(db_session)
    disclosures.upsert_disclosures(
        [
            {
                "source": "dart_mock",
                "external_id": "filing-1",
                "instrument_id": instrument.id,
                "event_time": NOW,
                "available_at": NOW,
                "ingested_at": NOW,
                "title": "Sample filing",
                "filing_type": "quarterly",
                "raw_payload": None,
            }
        ]
    )

    results = disclosures.get_disclosures_as_of(
        start=NOW - timedelta(days=1),
        end=NOW + timedelta(days=1),
        as_of=NOW,
        instrument_id=instrument.id,
    )
    assert len(results) == 1
    assert results[0].title == "Sample filing"


def test_strategy_registry_sync_and_get(migrated_schema, db_session) -> None:
    repo = StrategyRegistryRepository(db_session)
    repo.sync_from_spec(
        strategy_id="STR-TEST-001",
        version="0.1.0",
        name="Test strategy",
        status="research",
        source="manual",
        spec_created_at=NOW,
        spec_json={"strategy_id": "STR-TEST-001"},
    )
    row = repo.get(strategy_id="STR-TEST-001", version="0.1.0")
    assert row is not None
    assert row.status == "research"

    # Re-sync with an updated status - should update in place, not duplicate.
    repo.sync_from_spec(
        strategy_id="STR-TEST-001",
        version="0.1.0",
        name="Test strategy",
        status="pine_validated",
        source="manual",
        spec_created_at=NOW,
        spec_json={"strategy_id": "STR-TEST-001", "status": "pine_validated"},
    )
    updated = repo.get(strategy_id="STR-TEST-001", version="0.1.0")
    assert updated is not None
    assert updated.status == "pine_validated"
    assert len(repo.list_by_status("pine_validated")) == 1


def test_signals_upsert_and_point_in_time_read(migrated_schema, db_session) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="mock"
    )
    run_id, _ = ModelRunRepository(db_session).start_run(model_name="test-model")
    signals_repo = SignalRepository(db_session)
    signals_repo.upsert_signals(
        [
            {
                "model_run_id": run_id,
                "instrument_id": instrument.id,
                "event_time": NOW,
                "available_at": NOW,
                "ingested_at": NOW,
                "signal_value": Decimal("0.8"),
                "signal_label": "LONG",
                "payload": None,
                "source": "test-model",
            }
        ]
    )

    results = signals_repo.get_signals_as_of(
        instrument_id=instrument.id,
        start=NOW - timedelta(days=1),
        end=NOW + timedelta(days=1),
        as_of=NOW,
    )
    assert len(results) == 1
    assert results[0].signal_label == "LONG"


def test_backtest_run_lifecycle(migrated_schema, db_session) -> None:
    repo = BacktestRunRepository(db_session)
    run_id, created = repo.start_backtest(
        strategy_id="STR-TEST-001",
        strategy_version="0.1.0",
        period_start=NOW - timedelta(days=365),
        period_end=NOW,
        idempotency_key="backtest-2026-03-25",
    )
    assert created is True
    repo.finish_backtest(run_id, status="succeeded", metrics={"sharpe": 1.2})

    run_id_again, created_again = repo.start_backtest(
        strategy_id="STR-TEST-001",
        strategy_version="0.1.0",
        period_start=NOW - timedelta(days=365),
        period_end=NOW,
        idempotency_key="backtest-2026-03-25",
    )
    assert created_again is False
    assert run_id_again == run_id


def test_broker_order_idempotent_recording(migrated_schema, db_session) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="mock"
    )
    repo = BrokerOrderRepository(db_session)
    first_id, first_created = repo.record_order(
        broker_order_id="broker-1",
        source="toss_openapi",
        status="filled",
        instrument_id=instrument.id,
    )
    second_id, second_created = repo.record_order(
        broker_order_id="broker-1",
        source="toss_openapi",
        status="filled",
        instrument_id=instrument.id,
    )
    assert first_created is True
    assert second_created is False
    assert first_id == second_id


def test_position_snapshot_upsert_and_current_as_of(migrated_schema, db_session) -> None:
    instrument = InstrumentRepository(db_session).get_or_create(
        exchange="KRX", symbol="005930", source="mock"
    )
    positions_repo = PositionRepository(db_session)
    positions_repo.upsert_positions(
        [
            {
                "account_id": "acct-1",
                "instrument_id": instrument.id,
                "event_time": NOW,
                "available_at": NOW,
                "ingested_at": NOW,
                "quantity": Decimal("10"),
                "avg_price": Decimal("70000"),
                "source": "toss_openapi",
                "raw_payload": None,
            }
        ]
    )

    current = positions_repo.get_current_positions_as_of(account_id="acct-1", as_of=NOW)
    assert len(current) == 1
    assert current[0].quantity == Decimal("10")


def test_account_snapshot_upsert_and_latest_as_of(migrated_schema, db_session) -> None:
    account_repo = AccountSnapshotRepository(db_session)
    account_repo.upsert_snapshots(
        [
            {
                "account_id": "acct-1",
                "event_time": NOW,
                "available_at": NOW,
                "ingested_at": NOW,
                "cash_balance": None,
                "buying_power": None,
                "source": "toss_openapi",
                "raw_payload": {"result": "unconfirmed schema"},
            }
        ]
    )

    latest = account_repo.get_latest_as_of(account_id="acct-1", as_of=NOW)
    assert latest is not None
    assert latest.source == "toss_openapi"
