"""Mirrors `app.research.registry.StrategyRegistry` (file-based, source
of truth) into a queryable `strategy_registry` table.

This repository never reads/writes the JSON files itself - that stays
`app.research`'s job. `app.ingest.strategy_sync` (which depends on
both `app.research` and `app.db`) is what calls `sync_from_spec` after
loading a `StrategySpec` - see docs/architecture/0008-data-platform.md
for why the dependency runs one way only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.schema import strategy_registry


@dataclass(frozen=True)
class StrategyRegistryRow:
    strategy_id: str
    version: str
    name: str
    status: str
    source: str
    spec_created_at: datetime
    synced_at: datetime
    spec_json: dict[str, Any]


class StrategyRegistryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def sync_from_spec(
        self,
        *,
        strategy_id: str,
        version: str,
        name: str,
        status: str,
        source: str,
        spec_created_at: datetime,
        spec_json: dict[str, Any],
    ) -> None:
        insert_stmt = pg_insert(strategy_registry).values(
            strategy_id=strategy_id,
            version=version,
            name=name,
            status=status,
            source=source,
            spec_created_at=spec_created_at,
            spec_json=spec_json,
        )
        excluded = insert_stmt.excluded
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["strategy_id", "version"],
            set_={
                "name": excluded.name,
                "status": excluded.status,
                "source": excluded.source,
                "spec_json": excluded.spec_json,
                "synced_at": excluded.synced_at,
            },
        )
        self._session.execute(stmt)

    def get(self, *, strategy_id: str, version: str) -> StrategyRegistryRow | None:
        stmt = select(strategy_registry).where(
            strategy_registry.c.strategy_id == strategy_id,
            strategy_registry.c.version == version,
        )
        row = self._session.execute(stmt).mappings().one_or_none()
        if row is None:
            return None
        return StrategyRegistryRow(
            **{f: row[f] for f in StrategyRegistryRow.__dataclass_fields__}
        )

    def list_by_status(self, status: str) -> list[StrategyRegistryRow]:
        stmt = select(strategy_registry).where(strategy_registry.c.status == status)
        rows = self._session.execute(stmt).mappings().all()
        return [
            StrategyRegistryRow(**{f: row[f] for f in StrategyRegistryRow.__dataclass_fields__})
            for row in rows
        ]
