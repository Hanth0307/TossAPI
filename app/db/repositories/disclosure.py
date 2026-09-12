"""Disclosure (e.g. DART) events - idempotent on (source, external_id)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.schema import disclosure_events
from app.db.upsert import upsert_event_rows


@dataclass(frozen=True)
class DisclosureEventRow:
    source: str
    external_id: str
    instrument_id: int | None
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    title: str
    filing_type: str | None


class DisclosureRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_disclosures(self, rows: Sequence[Mapping[str, Any]]) -> int:
        return upsert_event_rows(
            self._session,
            disclosure_events,
            rows,
            natural_key_columns=["source", "external_id"],
            update_columns=["title", "filing_type", "instrument_id"],
        )

    def get_disclosures_as_of(
        self,
        *,
        start: datetime,
        end: datetime,
        as_of: datetime,
        instrument_id: int | None = None,
    ) -> list[DisclosureEventRow]:
        stmt = select(disclosure_events).where(
            disclosure_events.c.event_time >= start,
            disclosure_events.c.event_time <= end,
            disclosure_events.c.available_at <= as_of,
        )
        if instrument_id is not None:
            stmt = stmt.where(disclosure_events.c.instrument_id == instrument_id)
        stmt = stmt.order_by(disclosure_events.c.event_time)

        rows = self._session.execute(stmt).mappings().all()
        return [
            DisclosureEventRow(**{f: row[f] for f in DisclosureEventRow.__dataclass_fields__})
            for row in rows
        ]
