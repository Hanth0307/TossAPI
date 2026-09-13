"""Integration tests against real Postgres for
`app.ai_context.persistence` - `as_of`-gated reads and idempotent
upsert of AI Context annotations.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ai_context.extractor import ContextExtractionRequest
from app.ai_context.mock_extractor import MockContextExtractor
from app.ai_context.persistence import load_annotations_as_of, persist_annotations
from app.ai_context.schema import (
    EntityLink,
    EntityMatchStatus,
    EventKind,
    EventType,
    ExpectedDirection,
    ExtractionStatus,
    HorizonAssessment,
    ImpactDirection,
    ImpactDurationType,
    ImpactHorizon,
    LLMContextOutput,
    Novelty,
    SourceReliability,
)

_EVENT_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _horizon() -> ImpactHorizon:
    assessment = HorizonAssessment(expected_direction=ExpectedDirection.UP, confidence=0.55)
    return ImpactHorizon(
        one_day=assessment, five_day=assessment, ten_day=assessment, long_term=assessment
    )


def _output() -> LLMContextOutput:
    return LLMContextOutput(
        entities=[
            EntityLink(
                company_name="Samsung Electronics",
                ticker="005930",
                exchange="KRX",
                match_status=EntityMatchStatus.MATCHED,
                confidence=0.9,
            )
        ],
        event_type=EventType.EARNINGS,
        impact_direction=ImpactDirection.DIRECT,
        impact_duration=ImpactDurationType.ONE_OFF,
        novelty=Novelty.NEW,
        duplicate_cluster_id=None,
        source_reliability=SourceReliability.HIGH,
        impact_horizon=_horizon(),
        summary="Beat earnings estimates.",
        rationale="Operating profit exceeded consensus.",
    )


def test_persisted_annotation_round_trips_through_load_as_of(db_session: Session) -> None:
    extractor = MockContextExtractor(responses={"n-persist-1": _output()})
    request = ContextExtractionRequest(
        source="mock_news",
        external_id="n-persist-1",
        event_kind=EventKind.NEWS,
        event_time=_EVENT_TIME,
        headline_or_title="Samsung Q3 earnings beat",
        body="...",
    )
    result = extractor.extract(request)
    as_of = datetime(2026, 1, 1, 12, tzinfo=UTC)

    persist_annotations(db_session, [result], event_time=_EVENT_TIME, as_of=as_of)

    loaded = load_annotations_as_of(
        db_session,
        source="mock_news",
        external_id="n-persist-1",
        event_kind=EventKind.NEWS,
        as_of=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert len(loaded) == 1
    assert loaded[0].status == ExtractionStatus.OK
    assert loaded[0].event_type == EventType.EARNINGS
    assert loaded[0].entities[0].ticker == "005930"
    assert loaded[0].impact_horizon.five_day.expected_direction == ExpectedDirection.UP


def test_annotation_is_not_visible_before_its_available_at(db_session: Session) -> None:
    extractor = MockContextExtractor(responses={"n-persist-2": _output()})
    request = ContextExtractionRequest(
        source="mock_news",
        external_id="n-persist-2",
        event_kind=EventKind.NEWS,
        event_time=_EVENT_TIME,
        headline_or_title="headline",
        body=None,
    )
    result = extractor.extract(request)
    as_of = datetime(2026, 1, 1, 12, tzinfo=UTC)

    persist_annotations(db_session, [result], event_time=_EVENT_TIME, as_of=as_of)

    loaded_before = load_annotations_as_of(
        db_session,
        source="mock_news",
        external_id="n-persist-2",
        event_kind=EventKind.NEWS,
        as_of=datetime(2026, 1, 1, 6, tzinfo=UTC),
    )
    assert loaded_before == []


def test_unknown_result_persists_and_loads_with_parse_error(db_session: Session) -> None:
    extractor = MockContextExtractor(responses={"n-persist-3": ValueError("boom")})
    request = ContextExtractionRequest(
        source="mock_news",
        external_id="n-persist-3",
        event_kind=EventKind.NEWS,
        event_time=_EVENT_TIME,
        headline_or_title="headline",
        body=None,
    )
    result = extractor.extract(request)
    as_of = datetime(2026, 1, 1, 12, tzinfo=UTC)

    persist_annotations(db_session, [result], event_time=_EVENT_TIME, as_of=as_of)

    loaded = load_annotations_as_of(
        db_session,
        source="mock_news",
        external_id="n-persist-3",
        event_kind=EventKind.NEWS,
        as_of=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert len(loaded) == 1
    assert loaded[0].status == ExtractionStatus.UNKNOWN
    assert loaded[0].parse_error == "boom"
    assert loaded[0].event_type == EventType.UNKNOWN


def test_re_upserting_the_same_model_version_stays_a_single_row(db_session: Session) -> None:
    extractor = MockContextExtractor(responses={"n-persist-4": _output()})
    request = ContextExtractionRequest(
        source="mock_news",
        external_id="n-persist-4",
        event_kind=EventKind.NEWS,
        event_time=_EVENT_TIME,
        headline_or_title="headline",
        body=None,
    )
    result = extractor.extract(request)
    as_of = datetime(2026, 1, 1, 12, tzinfo=UTC)

    persist_annotations(db_session, [result], event_time=_EVENT_TIME, as_of=as_of)
    persist_annotations(db_session, [result], event_time=_EVENT_TIME, as_of=as_of)

    loaded = load_annotations_as_of(
        db_session,
        source="mock_news",
        external_id="n-persist-4",
        event_kind=EventKind.NEWS,
        as_of=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert len(loaded) == 1
