"""AI Context annotations (Phase 05) - plain observed-event table,
idempotent on (source, external_id, event_kind, model_name,
model_version). See `app.db.schema.ai_context_annotations` and ADR
0011.

Row/repository types here are intentionally untyped w.r.t.
`app.ai_context`'s pydantic/enum schema (plain `str`/`dict` fields
only) - `app.db` depends on `app.core` alone (ADR 0001), so the
`AIContextResult` <-> row conversion lives in `app.ai_context.
persistence`, not here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.schema import ai_context_annotations
from app.db.upsert import upsert_event_rows


@dataclass(frozen=True)
class AIContextAnnotationRow:
    source: str
    external_id: str
    event_kind: str
    model_name: str
    model_version: str
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    status: str
    event_type: str
    impact_direction: str
    impact_duration: str
    novelty: str
    duplicate_cluster_id: str | None
    source_reliability: str
    impact_horizon: dict[str, Any]
    entities: list[dict[str, Any]]
    summary: str
    rationale: str
    parse_error: str | None


_UPDATE_COLUMNS = [
    "status",
    "event_type",
    "impact_direction",
    "impact_duration",
    "novelty",
    "duplicate_cluster_id",
    "source_reliability",
    "impact_horizon",
    "entities",
    "summary",
    "rationale",
    "parse_error",
]


class AIContextRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_annotations(self, rows: Sequence[Mapping[str, Any]]) -> int:
        return upsert_event_rows(
            self._session,
            ai_context_annotations,
            rows,
            natural_key_columns=[
                "source", "external_id", "event_kind", "model_name", "model_version",
            ],
            update_columns=_UPDATE_COLUMNS,
        )

    def get_annotations_as_of(
        self,
        *,
        source: str,
        external_id: str,
        event_kind: str,
        as_of: datetime,
        model_name: str | None = None,
    ) -> list[AIContextAnnotationRow]:
        stmt = select(ai_context_annotations).where(
            ai_context_annotations.c.source == source,
            ai_context_annotations.c.external_id == external_id,
            ai_context_annotations.c.event_kind == event_kind,
            ai_context_annotations.c.available_at <= as_of,
        )
        if model_name is not None:
            stmt = stmt.where(ai_context_annotations.c.model_name == model_name)
        stmt = stmt.order_by(ai_context_annotations.c.event_time)

        rows = self._session.execute(stmt).mappings().all()
        fields = AIContextAnnotationRow.__dataclass_fields__
        return [AIContextAnnotationRow(**{f: row[f] for f in fields}) for row in rows]
