"""Operational audit log - ingestion outcomes, scheduler runs, quality
alerts. Idempotent on `dedup_key` when one is supplied (e.g. "job X's
run for 2026-09-12" so a retried scheduler tick doesn't double-log).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.repositories._idempotent_insert import get_or_insert
from app.db.schema import system_events


@dataclass(frozen=True)
class SystemEventRow:
    id: int
    event_type: str
    source: str
    severity: str
    message: str
    details: dict[str, Any] | None
    occurred_at: datetime
    ingested_at: datetime
    dedup_key: str | None


class SystemEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def log_event(
        self,
        *,
        event_type: str,
        source: str,
        severity: str,
        message: str,
        details: Mapping[str, Any] | None = None,
        occurred_at: datetime | None = None,
        dedup_key: str | None = None,
    ) -> tuple[int, bool]:
        values: dict[str, Any] = {
            "event_type": event_type,
            "source": source,
            "severity": severity,
            "message": message,
            "details": details,
            "dedup_key": dedup_key,
        }
        if occurred_at is not None:
            values["occurred_at"] = occurred_at

        if dedup_key is None:
            new_id = self._session.execute(
                system_events.insert().values(**values).returning(system_events.c.id)
            ).scalar_one()
            return new_id, True
        return get_or_insert(
            self._session, system_events, lookup={"dedup_key": dedup_key}, values=values
        )

    def list_recent(
        self, *, event_type: str | None = None, limit: int = 100
    ) -> list[SystemEventRow]:
        stmt = select(system_events)
        if event_type is not None:
            stmt = stmt.where(system_events.c.event_type == event_type)
        stmt = stmt.order_by(system_events.c.occurred_at.desc()).limit(limit)

        rows = self._session.execute(stmt).mappings().all()
        return [
            SystemEventRow(**{f: row[f] for f in SystemEventRow.__dataclass_fields__})
            for row in rows
        ]
