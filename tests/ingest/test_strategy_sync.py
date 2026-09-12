from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from app.db.repositories.strategy import StrategyRegistryRepository
from app.db.schema import strategy_registry
from app.ingest.strategy_sync import StrategyRegistrySync
from app.research.models import StrategySource, StrategySpec, StrategyStatus
from app.research.registry import StrategyRegistry


def _make_spec(strategy_id: str, version: str) -> StrategySpec:
    return StrategySpec(
        strategy_id=strategy_id,
        name="Test strategy",
        version=version,
        source=StrategySource.MANUAL,
        hypothesis="Placeholder hypothesis.",
        universe=["KOSPI:005930"],
        timeframe="1D",
        entry_rules=["rule"],
        exit_rules=["rule"],
        risk_assumptions=["assumption"],
        status=StrategyStatus.RESEARCH,
    )


def test_sync_one_mirrors_a_file_backed_spec_into_the_db(
    migrated_schema, db_session, tmp_path: Path
) -> None:
    file_registry = StrategyRegistry(base_dir=tmp_path)
    spec = _make_spec("STR-SYNC-001", "0.1.0")
    file_registry.save(spec)

    sync = StrategyRegistrySync(file_registry, StrategyRegistryRepository(db_session))
    sync.sync_one(strategy_id="STR-SYNC-001", version="0.1.0")

    row = StrategyRegistryRepository(db_session).get(strategy_id="STR-SYNC-001", version="0.1.0")
    assert row is not None
    assert row.status == "research"
    assert row.spec_json["strategy_id"] == "STR-SYNC-001"


def test_sync_all_mirrors_every_version_of_every_strategy(
    migrated_schema, db_session, tmp_path: Path
) -> None:
    file_registry = StrategyRegistry(base_dir=tmp_path)
    file_registry.save(_make_spec("STR-SYNC-001", "0.1.0"))
    file_registry.save(_make_spec("STR-SYNC-001", "0.2.0"))
    file_registry.save(_make_spec("STR-SYNC-002", "0.1.0"))

    sync = StrategyRegistrySync(file_registry, StrategyRegistryRepository(db_session))
    synced_count = sync.sync_all()

    assert synced_count == 3
    repo = StrategyRegistryRepository(db_session)
    assert repo.get(strategy_id="STR-SYNC-001", version="0.1.0") is not None
    assert repo.get(strategy_id="STR-SYNC-001", version="0.2.0") is not None
    assert repo.get(strategy_id="STR-SYNC-002", version="0.1.0") is not None


def test_resyncing_the_same_spec_updates_in_place_not_duplicates(
    migrated_schema, db_session, tmp_path: Path
) -> None:
    file_registry = StrategyRegistry(base_dir=tmp_path)
    file_registry.save(_make_spec("STR-SYNC-001", "0.1.0"))

    sync = StrategyRegistrySync(file_registry, StrategyRegistryRepository(db_session))
    sync.sync_one(strategy_id="STR-SYNC-001", version="0.1.0")
    sync.sync_one(strategy_id="STR-SYNC-001", version="0.1.0")  # resume-after-restart style re-run

    count = db_session.execute(select(func.count()).select_from(strategy_registry)).scalar_one()
    assert count == 1
