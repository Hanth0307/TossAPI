"""Mirrors `app.research`'s file-based Strategy Registry into the
`strategy_registry` table (`app.db.repositories.strategy`).

The JSON files under `research/strategies/` stay the source of truth
(ADR 0006) - this only keeps a queryable copy in sync so other tables
(`signals`, `model_runs`, `backtest_runs`) can join against it. This is
the one place `app.research` and `app.db` meet; neither package
depends on the other directly (see `app.research`'s own `__init__.py`
and docs/architecture/0008-data-platform.md).
"""

from __future__ import annotations

import json

from app.db.repositories.strategy import StrategyRegistryRepository
from app.research.registry import StrategyRegistry


class StrategyRegistrySync:
    def __init__(
        self, file_registry: StrategyRegistry, db_repository: StrategyRegistryRepository
    ) -> None:
        self._file_registry = file_registry
        self._db_repository = db_repository

    def sync_one(self, *, strategy_id: str, version: str) -> None:
        spec = self._file_registry.load(strategy_id, version)
        self._db_repository.sync_from_spec(
            strategy_id=spec.strategy_id,
            version=spec.version,
            name=spec.name,
            status=spec.status.value,
            source=spec.source.value,
            spec_created_at=spec.created_at,
            spec_json=json.loads(spec.model_dump_json()),
        )

    def sync_all(self) -> int:
        count = 0
        for strategy_id in self._file_registry.list_strategy_ids():
            for version in self._file_registry.list_versions(strategy_id):
                self.sync_one(strategy_id=strategy_id, version=version)
                count += 1
        return count
