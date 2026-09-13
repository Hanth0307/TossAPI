"""`AIContextResult` <-> `app.db.repositories.ai_context` row
conversion. This is the one place `app.ai_context` touches `app.db` -
`schema.py`/`extractor.py`/`claude_extractor.py`/`mock_extractor.py`
are pure logic with no database import, mirroring `app.scanners`'s
pipeline/persistence split.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.ai_context.schema import (
    AIContextResult,
    EntityLink,
    EventKind,
    EventType,
    ExtractionStatus,
    ImpactDirection,
    ImpactDurationType,
    ImpactHorizon,
    Novelty,
    SourceReliability,
)
from app.db.repositories.ai_context import AIContextAnnotationRow, AIContextRepository

_ENTITY_LIST_ADAPTER: TypeAdapter[list[EntityLink]] = TypeAdapter(list[EntityLink])


def persist_annotations(
    session: Session, results: Sequence[AIContextResult], *, event_time: datetime, as_of: datetime
) -> int:
    """`event_time` is the underlying news/disclosure item's own
    `event_time` (when the article/filing happened) - `available_at`
    is `as_of` (when this annotation became knowable: the moment it
    was generated), never backdated to the article's own event_time,
    so a point-in-time read can never see an annotation before it was
    actually produced.
    """
    repository = AIContextRepository(session)
    rows = [
        {
            "source": result.source,
            "external_id": result.external_id,
            "event_kind": result.event_kind.value,
            "model_name": result.model_name,
            "model_version": result.model_version,
            "event_time": event_time,
            "available_at": as_of,
            "ingested_at": result.generated_at,
            "status": result.status.value,
            "event_type": result.event_type.value,
            "impact_direction": result.impact_direction.value,
            "impact_duration": result.impact_duration.value,
            "novelty": result.novelty.value,
            "duplicate_cluster_id": result.duplicate_cluster_id,
            "source_reliability": result.source_reliability.value,
            "impact_horizon": result.impact_horizon.model_dump(mode="json"),
            "entities": [e.model_dump(mode="json") for e in result.entities],
            "summary": result.summary,
            "rationale": result.rationale,
            "parse_error": result.parse_error,
        }
        for result in results
    ]
    return repository.upsert_annotations(rows)


def _to_result(row: AIContextAnnotationRow) -> AIContextResult:
    return AIContextResult(
        status=ExtractionStatus(row.status),
        source=row.source,
        external_id=row.external_id,
        event_kind=EventKind(row.event_kind),
        model_name=row.model_name,
        model_version=row.model_version,
        generated_at=row.ingested_at,
        entities=_ENTITY_LIST_ADAPTER.validate_python(row.entities),
        event_type=EventType(row.event_type),
        impact_direction=ImpactDirection(row.impact_direction),
        impact_duration=ImpactDurationType(row.impact_duration),
        novelty=Novelty(row.novelty),
        duplicate_cluster_id=row.duplicate_cluster_id,
        source_reliability=SourceReliability(row.source_reliability),
        impact_horizon=ImpactHorizon.model_validate(row.impact_horizon),
        summary=row.summary,
        rationale=row.rationale,
        parse_error=row.parse_error,
    )


def load_annotations_as_of(
    session: Session,
    *,
    source: str,
    external_id: str,
    event_kind: EventKind,
    as_of: datetime,
    model_name: str | None = None,
) -> list[AIContextResult]:
    repository = AIContextRepository(session)
    rows = repository.get_annotations_as_of(
        source=source,
        external_id=external_id,
        event_kind=event_kind.value,
        as_of=as_of,
        model_name=model_name,
    )
    return [_to_result(row) for row in rows]
