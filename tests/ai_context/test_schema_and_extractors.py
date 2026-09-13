"""Fixed-fixture tests for the `AIContextResult` schema and the
extractor contract shared by every `ContextExtractor` implementation -
no database, no network. Proves the phase's core requirement: an LLM
response failure or parse failure becomes an explicit `unknown` result
with every classification field at its `UNKNOWN` variant, never a
raised exception and never a guessed value.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.ai_context.claude_extractor import ClaudeContextExtractor
from app.ai_context.extractor import ContextExtractionRequest, KnownInstrument
from app.ai_context.mock_extractor import MockContextExtractor
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

_AS_OF = datetime(2026, 1, 1, tzinfo=UTC)


def _horizon(direction: ExpectedDirection = ExpectedDirection.UP) -> ImpactHorizon:
    assessment = HorizonAssessment(expected_direction=direction, confidence=0.6)
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


def _request(
    external_id: str, known_instruments: tuple[KnownInstrument, ...] = ()
) -> ContextExtractionRequest:
    return ContextExtractionRequest(
        source="mock_news",
        external_id=external_id,
        event_kind=EventKind.NEWS,
        event_time=_AS_OF,
        headline_or_title="headline",
        body="body",
        known_instruments=known_instruments,
    )


def test_mock_extractor_returns_ok_result_for_configured_success() -> None:
    extractor = MockContextExtractor(responses={"n-1": _output()})
    result = extractor.extract(_request("n-1"))

    assert result.status == ExtractionStatus.OK
    assert result.event_type == EventType.EARNINGS
    assert result.entities[0].ticker == "005930"
    assert result.parse_error is None


def test_mock_extractor_returns_unknown_result_for_configured_exception() -> None:
    extractor = MockContextExtractor(responses={"n-2": ValueError("simulated timeout")})
    result = extractor.extract(_request("n-2"))

    assert result.status == ExtractionStatus.UNKNOWN
    assert result.parse_error == "simulated timeout"
    # Every classification field defaults to its UNKNOWN variant - never guessed.
    assert result.event_type == EventType.UNKNOWN
    assert result.impact_direction == ImpactDirection.UNKNOWN
    assert result.impact_duration == ImpactDurationType.UNKNOWN
    assert result.novelty == Novelty.UNKNOWN
    assert result.source_reliability == SourceReliability.UNKNOWN
    assert result.entities == []
    assert result.impact_horizon.one_day.expected_direction == ExpectedDirection.UNKNOWN
    assert result.impact_horizon.five_day.expected_direction == ExpectedDirection.UNKNOWN
    assert result.impact_horizon.ten_day.expected_direction == ExpectedDirection.UNKNOWN
    assert result.impact_horizon.long_term.expected_direction == ExpectedDirection.UNKNOWN


def test_mock_extractor_returns_unknown_result_when_no_response_configured() -> None:
    extractor = MockContextExtractor()
    result = extractor.extract(_request("n-unconfigured"))

    assert result.status == ExtractionStatus.UNKNOWN
    assert "no mock response configured" in (result.parse_error or "")


def test_entity_link_never_requires_a_ticker_for_unmatched_status() -> None:
    entity = EntityLink(
        company_name="Some Small Company",
        ticker=None,
        exchange=None,
        match_status=EntityMatchStatus.UNMATCHED,
        confidence=0.1,
    )
    assert entity.ticker is None
    assert entity.match_status == EntityMatchStatus.UNMATCHED


def test_llm_context_output_requires_every_field() -> None:
    with pytest.raises(ValidationError):
        LLMContextOutput(
            entities=[],
            event_type=EventType.EARNINGS,
            # missing impact_direction, impact_duration, novelty, ... - must fail
        )


def test_impact_horizon_carries_all_four_required_periods() -> None:
    horizon = _horizon(direction=ExpectedDirection.DOWN)
    assert horizon.one_day.expected_direction == ExpectedDirection.DOWN
    assert horizon.five_day.expected_direction == ExpectedDirection.DOWN
    assert horizon.ten_day.expected_direction == ExpectedDirection.DOWN
    assert horizon.long_term.expected_direction == ExpectedDirection.DOWN


def test_known_instruments_are_passed_through_the_request_unmodified() -> None:
    instruments = (KnownInstrument(symbol="005930", exchange="KRX", name="Samsung Electronics"),)
    request = _request("n-3", known_instruments=instruments)
    assert request.known_instruments == instruments


class _FakeParsedMessage:
    def __init__(self, parsed_output: LLMContextOutput) -> None:
        self.parsed_output = parsed_output


class _FakeMessagesOk:
    def __init__(self, output: LLMContextOutput) -> None:
        self._output = output

    def parse(self, **kwargs: object) -> _FakeParsedMessage:
        assert kwargs["output_format"] is LLMContextOutput
        return _FakeParsedMessage(self._output)


class _FakeClientOk:
    def __init__(self, output: LLMContextOutput) -> None:
        self.messages = _FakeMessagesOk(output)


class _FakeMessagesRaising:
    def parse(self, **kwargs: object) -> _FakeParsedMessage:
        raise TimeoutError("connection timed out")


class _FakeClientRaising:
    def __init__(self) -> None:
        self.messages = _FakeMessagesRaising()


def test_claude_extractor_returns_ok_result_when_client_parses_successfully() -> None:
    extractor = ClaudeContextExtractor(
        api_key="unused", model="claude-opus-5", client=_FakeClientOk(_output())
    )
    result = extractor.extract(_request("n-4"))

    assert result.status == ExtractionStatus.OK
    assert result.model_name == "claude"
    assert result.model_version == "claude-opus-5"
    assert result.event_type == EventType.EARNINGS


def test_claude_extractor_isolates_any_client_failure_into_unknown() -> None:
    """This is the isolation boundary the phase requires: a raised
    exception from the LLM client must never propagate - it becomes an
    explicit unknown result instead."""
    extractor = ClaudeContextExtractor(
        api_key="unused", model="claude-opus-5", client=_FakeClientRaising()
    )
    result = extractor.extract(_request("n-5"))

    assert result.status == ExtractionStatus.UNKNOWN
    assert "connection timed out" in (result.parse_error or "")
    assert result.event_type == EventType.UNKNOWN
