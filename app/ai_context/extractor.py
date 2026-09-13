"""`ContextExtractor` Protocol and the request/result-building helpers
shared by every concrete extractor (`claude_extractor.py`,
`mock_extractor.py`) - so "wrap a raw LLM output into the fixed
`AIContextResult` shape" and "fall back to an explicit unknown result"
are implemented exactly once, not duplicated per extractor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.ai_context.schema import (
    AIContextResult,
    EventKind,
    ExtractionStatus,
    LLMContextOutput,
)


@dataclass(frozen=True)
class KnownInstrument:
    """One candidate for entity linking - the LLM is shown a list of
    these (not asked to invent a ticker from scratch)."""

    symbol: str
    exchange: str
    name: str | None


@dataclass(frozen=True)
class ContextExtractionRequest:
    source: str
    external_id: str
    event_kind: EventKind
    event_time: datetime
    headline_or_title: str
    body: str | None
    known_instruments: tuple[KnownInstrument, ...] = ()


class ContextExtractor(Protocol):
    model_name: str
    model_version: str

    def extract(self, request: ContextExtractionRequest) -> AIContextResult: ...


def ok_result(
    *, request: ContextExtractionRequest, model_name: str, model_version: str,
    output: LLMContextOutput,
) -> AIContextResult:
    return AIContextResult(
        status=ExtractionStatus.OK,
        source=request.source,
        external_id=request.external_id,
        event_kind=request.event_kind,
        model_name=model_name,
        model_version=model_version,
        generated_at=datetime.now(UTC),
        entities=output.entities,
        event_type=output.event_type,
        impact_direction=output.impact_direction,
        impact_duration=output.impact_duration,
        novelty=output.novelty,
        duplicate_cluster_id=output.duplicate_cluster_id,
        source_reliability=output.source_reliability,
        impact_horizon=output.impact_horizon,
        summary=output.summary,
        rationale=output.rationale,
        parse_error=None,
    )


def unknown_result(
    *, request: ContextExtractionRequest, model_name: str, model_version: str,
    parse_error: str,
) -> AIContextResult:
    """Every field defaults to its `UNKNOWN` variant (see
    `AIContextResult`'s dataclass defaults) - this is the single place
    an extraction failure becomes an explicit, typed "unknown" rather
    than a raised exception or a guessed value."""
    return AIContextResult(
        status=ExtractionStatus.UNKNOWN,
        source=request.source,
        external_id=request.external_id,
        event_kind=request.event_kind,
        model_name=model_name,
        model_version=model_version,
        generated_at=datetime.now(UTC),
        parse_error=parse_error,
    )
