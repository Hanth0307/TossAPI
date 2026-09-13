"""Pure (no database) tests for `SignalInput`/`build_signal_input` -
every combination of present/missing inputs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.ai_context.schema import AIContextResult, EventKind, ExtractionStatus
from app.regime.classifier import BreadthState, RegimeAssessment, TrendState, VolatilityLevel
from app.signals.schema import QuantProbability, build_signal_input

_AS_OF = datetime(2026, 1, 1, tzinfo=UTC)
_GENERATED_AT = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)


def _ai_context_result() -> AIContextResult:
    return AIContextResult(
        status=ExtractionStatus.OK,
        source="mock_news",
        external_id="n-1",
        event_kind=EventKind.NEWS,
        model_name="mock",
        model_version="0.0.0",
        generated_at=_AS_OF,
    )


def _quant_probability() -> QuantProbability:
    return QuantProbability(
        model_name="quant_baseline",
        model_version="logreg_v1",
        feature_schema_version="1.0.0",
        label_definition_version="fwd_return_5d_v1",
        probability=0.73,
        as_of=_AS_OF,
    )


def _regime() -> RegimeAssessment:
    return RegimeAssessment(
        as_of=_AS_OF,
        trend=TrendState.UPTREND,
        volatility_level=VolatilityLevel.NORMAL,
        breadth=BreadthState.EXPANDING,
        observed_return=None,
        observed_volatility=None,
        observed_breadth_ratio=None,
    )


def test_signal_input_with_all_three_inputs_present() -> None:
    signal = build_signal_input(
        instrument_id=1, symbol="005930", as_of=_AS_OF, generated_at=_GENERATED_AT,
        ai_context=[_ai_context_result()], quant_probability=_quant_probability(), regime=_regime(),
    )
    assert signal.has_ai_context is True
    assert signal.has_quant_probability is True
    assert signal.has_regime is True
    assert signal.quant_probability is not None
    assert signal.quant_probability.probability == 0.73


def test_signal_input_with_no_inputs_present_uses_empty_not_fabricated_values() -> None:
    signal = build_signal_input(
        instrument_id=1, symbol="005930", as_of=_AS_OF, generated_at=_GENERATED_AT,
    )
    assert signal.has_ai_context is False
    assert signal.has_quant_probability is False
    assert signal.has_regime is False
    assert signal.ai_context == []
    assert signal.quant_probability is None
    assert signal.regime is None


def test_signal_input_with_partial_inputs() -> None:
    signal = build_signal_input(
        instrument_id=1, symbol="005930", as_of=_AS_OF, generated_at=_GENERATED_AT,
        quant_probability=_quant_probability(),
    )
    assert signal.has_quant_probability is True
    assert signal.has_ai_context is False
    assert signal.has_regime is False


def test_signal_input_never_has_an_order_shaped_field() -> None:
    """A `SignalInput` must never be mistaken for an order request -
    no side/quantity/order_type/price field exists on it."""
    signal = build_signal_input(
        instrument_id=1, symbol="005930", as_of=_AS_OF, generated_at=_GENERATED_AT,
    )
    field_names = set(signal.__dataclass_fields__)
    assert not field_names & {"order", "side", "quantity", "order_type", "limit_price"}
