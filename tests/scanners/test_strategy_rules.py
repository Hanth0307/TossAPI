"""Fixed-fixture PASS/FAIL reproduction for `StrategyScanner` - no
database. Also covers `Candidate`'s introspection properties.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.scanners.candidate import Candidate
from app.scanners.events import EventDetection
from app.scanners.features import FeatureSet
from app.scanners.strategy_rules import (
    Comparator,
    StrategyCondition,
    StrategyRuleSet,
    StrategyScanner,
)
from app.scanners.universe import UniverseFilterResult

_AS_OF = datetime(2026, 1, 1, tzinfo=UTC)


def test_strategy_scanner_all_conditions_pass() -> None:
    rule_set = StrategyRuleSet(
        strategy_id="STR-001",
        strategy_version="1.0.0",
        conditions=[
            StrategyCondition(
                name="volume_above_threshold",
                field="volume",
                comparator=Comparator.GT,
                threshold=Decimal("1000"),
                description="volume above 1000",
            )
        ],
    )
    feature_set = FeatureSet(
        instrument_symbol="005930",
        as_of=_AS_OF,
        data_source="test",
        values={"volume": Decimal("2000")},
    )
    result = StrategyScanner().evaluate(rule_set, feature_set=feature_set)
    assert result.passed is True
    assert result.condition_results[0].passed is True
    assert result.strategy_id == "STR-001"
    assert result.strategy_version == "1.0.0"


def test_strategy_scanner_records_failure_reason_when_condition_fails() -> None:
    rule_set = StrategyRuleSet(
        strategy_id="STR-001",
        strategy_version="1.0.0",
        conditions=[
            StrategyCondition(
                name="volume_above_threshold",
                field="volume",
                comparator=Comparator.GT,
                threshold=Decimal("1000"),
                description="volume above 1000",
            )
        ],
    )
    feature_set = FeatureSet(
        instrument_symbol="005930",
        as_of=_AS_OF,
        data_source="test",
        values={"volume": Decimal("500")},
    )
    result = StrategyScanner().evaluate(rule_set, feature_set=feature_set)
    assert result.passed is False
    assert result.condition_results[0].passed is False
    assert result.condition_results[0].reason is not None


def test_strategy_scanner_fails_missing_feature_without_guessing() -> None:
    rule_set = StrategyRuleSet(
        strategy_id="STR-001",
        strategy_version="1.0.0",
        conditions=[
            StrategyCondition(
                name="missing_feature",
                field="not_computed",
                comparator=Comparator.GT,
                threshold=Decimal("0"),
                description="a feature that was never computed",
            )
        ],
    )
    feature_set = FeatureSet(
        instrument_symbol="005930", as_of=_AS_OF, data_source="test", values={}
    )
    result = StrategyScanner().evaluate(rule_set, feature_set=feature_set)
    assert result.passed is False
    assert result.condition_results[0].observed_value is None
    assert "not present" in (result.condition_results[0].reason or "")


def test_strategy_version_change_produces_separate_result_object() -> None:
    """Two evaluations against different `strategy_version`s never
    collapse into "the same result" - each carries its own version."""
    rule_set_v1 = StrategyRuleSet(strategy_id="STR-001", strategy_version="1.0.0", conditions=[])
    rule_set_v2 = StrategyRuleSet(strategy_id="STR-001", strategy_version="2.0.0", conditions=[])
    feature_set = FeatureSet(
        instrument_symbol="005930", as_of=_AS_OF, data_source="test", values={}
    )
    scanner = StrategyScanner()
    result_v1 = scanner.evaluate(rule_set_v1, feature_set=feature_set)
    result_v2 = scanner.evaluate(rule_set_v2, feature_set=feature_set)
    assert result_v1.strategy_version == "1.0.0"
    assert result_v2.strategy_version == "2.0.0"
    assert result_v1 != result_v2


def _candidate(*, qualified: bool, universe_passed: bool, event_detected: bool) -> Candidate:
    return Candidate(
        instrument_id=1,
        symbol="005930",
        exchange="KRX",
        as_of=_AS_OF,
        data_source="test",
        universe_results=[
            UniverseFilterResult("liquidity", universe_passed, Decimal("1"), Decimal("1"), None)
        ],
        event_detections=[
            EventDetection("price_gap", event_detected, Decimal("1"), Decimal("1"), None, None)
        ],
        strategy_result=None,
        qualified=qualified,
        generated_at=_AS_OF,
    )


def test_candidate_passed_universe_property() -> None:
    candidate = _candidate(qualified=False, universe_passed=True, event_detected=False)
    assert candidate.passed_universe is True


def test_candidate_has_triggering_event_property() -> None:
    candidate = _candidate(qualified=False, universe_passed=True, event_detected=True)
    assert candidate.has_triggering_event is True


def test_candidate_passed_strategy_is_false_without_a_strategy_result() -> None:
    candidate = _candidate(qualified=False, universe_passed=True, event_detected=True)
    assert candidate.passed_strategy is False


def test_candidate_is_never_interpreted_as_an_order() -> None:
    """A `Candidate` has no field named order/quantity/side/price -
    nothing in this dataclass can be mistaken for an order request."""
    candidate = _candidate(qualified=True, universe_passed=True, event_detected=True)
    field_names = {f for f in candidate.__dataclass_fields__}
    assert not field_names & {"order", "side", "quantity", "order_type", "limit_price"}
