"""Disclosure (e.g. DART) events - append-only revisions, idempotent
on (source, external_id, available_at).

A filing can be amended/restated after its original publication.
`upsert_disclosures` never overwrites a prior revision - see
`app.db.upsert.append_revision_rows` and ADR 0009.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories._revisions import select_latest_revision_as_of
from app.db.schema import disclosure_events
from app.db.upsert import append_revision_rows


@dataclass(frozen=True)
class DisclosureEventRow:
    source: str
    external_id: str
    instrument_id: int | None
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    revision: int
    title: str
    filing_type: str | None


class DisclosureRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_disclosures(self, rows: Sequence[Mapping[str, Any]]) -> int:
        return append_revision_rows(
            self._session,
            disclosure_events,
            rows,
            logical_key_columns=["source", "external_id"],
        )

    def get_disclosures_as_of(
        self,
        *,
        start: datetime,
        end: datetime,
        as_of: datetime,
        instrument_id: int | None = None,
    ) -> list[DisclosureEventRow]:
        filters = [
            disclosure_events.c.event_time >= start,
            disclosure_events.c.event_time <= end,
        ]
        if instrument_id is not None:
            filters.append(disclosure_events.c.instrument_id == instrument_id)

        rows = select_latest_revision_as_of(
            self._session,
            disclosure_events,
            logical_key_columns=["source", "external_id"],
            filters=filters,
            as_of=as_of,
        )
        return [
            DisclosureEventRow(**{f: row[f] for f in DisclosureEventRow.__dataclass_fields__})
            for row in rows
        ]
