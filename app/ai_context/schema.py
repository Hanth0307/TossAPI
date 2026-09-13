"""The fixed AI Context output schema (Phase 05, see ADR 0011).

Two schemas, deliberately separate:

- `LLMContextOutput` (pydantic) is the shape an LLM is constrained to
  produce - passed as `output_format=LLMContextOutput` to
  `client.messages.parse` (see `app.ai_context.claude_extractor`).
  Nothing outside `app.ai_context` ever asks an LLM for a different
  shape, and nothing here asks an LLM for a sentiment/quality score -
  only structured classification fields.
- `AIContextResult` (a frozen dataclass, mirroring this codebase's
  `*Row` convention - see `app.db.repositories`) is what every
  extractor returns and every downstream consumer reads. It is
  intentionally **flat and total**: every field always has a value,
  never `None` standing in for "the LLM didn't say." A failed or
  unparseable LLM response produces the *same* `AIContextResult` shape
  with every classification field set to its explicit `UNKNOWN`
  variant, `status=ExtractionStatus.UNKNOWN`, and `parse_error` set -
  so a consumer never needs a null-check to find out extraction
  failed, only a `status` check, and can never mistake "the model
  didn't know" for a real value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EventKind(StrEnum):
    NEWS = "news"
    DISCLOSURE = "disclosure"


class ExtractionStatus(StrEnum):
    OK = "ok"
    UNKNOWN = "unknown"


class EventType(StrEnum):
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    MERGER_ACQUISITION = "merger_acquisition"
    REGULATORY = "regulatory"
    PRODUCT = "product"
    MANAGEMENT_CHANGE = "management_change"
    LITIGATION = "litigation"
    MACRO = "macro"
    SUPPLY_CHAIN = "supply_chain"
    OTHER = "other"
    UNKNOWN = "unknown"


class ImpactDirection(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    UNKNOWN = "unknown"


class ImpactDurationType(StrEnum):
    ONE_OFF = "one_off"
    STRUCTURAL = "structural"
    UNKNOWN = "unknown"


class Novelty(StrEnum):
    NEW = "new"
    DUPLICATE = "duplicate"
    FOLLOW_UP = "follow_up"
    UNKNOWN = "unknown"


class SourceReliability(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ExpectedDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class EntityMatchStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


class EntityLink(BaseModel):
    """One company/ticker the LLM believes the text refers to.

    `match_status` is never guessed toward `matched` - if the model is
    not confident which known instrument (if any) this refers to, it
    must report `ambiguous`/`unmatched` and leave `ticker`/`exchange`
    unset rather than inventing a plausible-looking one.
    """

    company_name: str
    ticker: str | None = None
    exchange: str | None = None
    match_status: EntityMatchStatus
    confidence: float = Field(ge=0.0, le=1.0)


class HorizonAssessment(BaseModel):
    expected_direction: ExpectedDirection
    confidence: float = Field(ge=0.0, le=1.0)


class ImpactHorizon(BaseModel):
    """Fixed structured output for exactly the four horizons the phase
    requires: 1 day / 5 day / 10 day / long-term."""

    one_day: HorizonAssessment
    five_day: HorizonAssessment
    ten_day: HorizonAssessment
    long_term: HorizonAssessment


def _unknown_horizon() -> ImpactHorizon:
    unknown = HorizonAssessment(expected_direction=ExpectedDirection.UNKNOWN, confidence=0.0)
    return ImpactHorizon(one_day=unknown, five_day=unknown, ten_day=unknown, long_term=unknown)


class LLMContextOutput(BaseModel):
    """The schema an LLM is constrained to produce via
    `client.messages.parse(output_format=LLMContextOutput)`. Every
    field is required - the model must make an explicit `unknown`/
    `unmatched` choice rather than omitting a field.
    """

    entities: list[EntityLink]
    event_type: EventType
    impact_direction: ImpactDirection
    impact_duration: ImpactDurationType
    novelty: Novelty
    duplicate_cluster_id: str | None
    source_reliability: SourceReliability
    impact_horizon: ImpactHorizon
    summary: str
    rationale: str


@dataclass(frozen=True)
class AIContextResult:
    """What every `ContextExtractor` returns - always this exact shape,
    whether extraction succeeded or not. See module docstring.
    """

    status: ExtractionStatus
    source: str
    external_id: str
    event_kind: EventKind
    model_name: str
    model_version: str
    generated_at: datetime
    entities: list[EntityLink] = field(default_factory=list)
    event_type: EventType = EventType.UNKNOWN
    impact_direction: ImpactDirection = ImpactDirection.UNKNOWN
    impact_duration: ImpactDurationType = ImpactDurationType.UNKNOWN
    novelty: Novelty = Novelty.UNKNOWN
    duplicate_cluster_id: str | None = None
    source_reliability: SourceReliability = SourceReliability.UNKNOWN
    impact_horizon: ImpactHorizon = field(default_factory=_unknown_horizon)
    summary: str = ""
    rationale: str = ""
    parse_error: str | None = None
