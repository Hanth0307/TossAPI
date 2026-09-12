"""News events - idempotent on (source, external_id)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.schema import news_events
from app.db.upsert import upsert_event_rows


@dataclass(frozen=True)
class NewsEventRow:
    source: str
    external_id: str
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    headline: str
    body: str | None
    related_symbols: list[str] | None


class NewsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_news(self, rows: Sequence[Mapping[str, Any]]) -> int:
        return upsert_event_rows(
            self._session,
            news_events,
            rows,
            natural_key_columns=["source", "external_id"],
            update_columns=["headline", "body", "related_symbols"],
        )

    def get_news_as_of(
        self, *, start: datetime, end: datetime, as_of: datetime, symbol: str | None = None
    ) -> list[NewsEventRow]:
        stmt = select(news_events).where(
            news_events.c.event_time >= start,
            news_events.c.event_time <= end,
            news_events.c.available_at <= as_of,
        )
        if symbol is not None:
            stmt = stmt.where(news_events.c.related_symbols.contains([symbol]))
        stmt = stmt.order_by(news_events.c.event_time)

        rows = self._session.execute(stmt).mappings().all()
        return [
            NewsEventRow(**{f: row[f] for f in NewsEventRow.__dataclass_fields__}) for row in rows
        ]
