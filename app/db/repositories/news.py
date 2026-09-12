"""News events - append-only revisions, idempotent on (source, external_id, available_at).

A news source can issue a correction to an already-published article.
`upsert_news` never overwrites a prior revision's headline/body - see
`app.db.upsert.append_revision_rows` and ADR 0009.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories._revisions import select_latest_revision_as_of
from app.db.schema import news_events
from app.db.upsert import append_revision_rows


@dataclass(frozen=True)
class NewsEventRow:
    source: str
    external_id: str
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    revision: int
    headline: str
    body: str | None
    related_symbols: list[str] | None


class NewsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_news(self, rows: Sequence[Mapping[str, Any]]) -> int:
        return append_revision_rows(
            self._session, news_events, rows, logical_key_columns=["source", "external_id"]
        )

    def get_news_as_of(
        self, *, start: datetime, end: datetime, as_of: datetime, symbol: str | None = None
    ) -> list[NewsEventRow]:
        filters = [
            news_events.c.event_time >= start,
            news_events.c.event_time <= end,
        ]
        if symbol is not None:
            filters.append(news_events.c.related_symbols.contains([symbol]))

        rows = select_latest_revision_as_of(
            self._session,
            news_events,
            logical_key_columns=["source", "external_id"],
            filters=filters,
            as_of=as_of,
        )
        return [
            NewsEventRow(**{f: row[f] for f in NewsEventRow.__dataclass_fields__}) for row in rows
        ]
