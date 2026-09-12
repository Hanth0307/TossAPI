"""Strategy Scanner: evaluates a `StrategyRuleSet`'s conditions against
a computed `app.scanners.features.FeatureSet`, recording PASS/FAIL and
the actual observed value per condition.

`StrategyRuleSet` is a deliberately separate, structured, human-
authored companion to `app.research.models.StrategySpec` (Phase 01) -
it is never derived by parsing `StrategySpec.entry_rules`/`exit_rules`
prose. Those remain free-text research documentation (ADR 0006);
turning an idea into a machine-checkable condition is a distinct
authoring step a person performs, referencing the same
`(strategy_id, strategy_version)` for traceability so a scan result can
always be traced back to the research record it implements.

Every `StrategyScanResult` records `as_of`, `data_source`,
`strategy_id`, and `strategy_version` alongside each condition's
PASS/FAIL and observed value and failure reason, per the phase
requirement that a Strategy Scanner result must be reproducible and
attributable, not just a boolean.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.scanners.features import FeatureSet


class Comparator(StrEnum):
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    NEQ = "neq"


_COMPARATOR_FUNCS: dict[Comparator, Callable[[Decimal, Decimal], bool]] = {
    Comparator.GT: lambda observed, threshold: observed > threshold,
    Comparator.GTE: lambda observed, threshold: observed >= threshold,
    Comparator.LT: lambda observed, threshold: observed < threshold,
    Comparator.LTE: lambda observed, threshold: observed <= threshold,
    Comparator.EQ: lambda observed, threshold: observed == threshold,
    Comparator.NEQ: lambda observed, threshold: observed != threshold,
}


@dataclass(frozen=True)
class StrategyCondition:
    name: str
    field: str
    comparator: Comparator
    threshold: Decimal
    description: str


@dataclass(frozen=True)
class StrategyRuleSet:
    strategy_id: str
    strategy_version: str
    conditions: list[StrategyCondition]


@dataclass(frozen=True)
class StrategyConditionResult:
    condition_name: str
    field: str
    passed: bool
    observed_value: Decimal | None
    threshold: Decimal
    reason: str | None


@dataclass(frozen=True)
class StrategyScanResult:
    strategy_id: str
    strategy_version: str
    instrument_symbol: str
    as_of: datetime
    data_source: str
    condition_results: list[StrategyConditionResult]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.condition_results)


class StrategyScanner:
    """Evaluates a `StrategyRuleSet`'s conditions against a
    `FeatureSet`. Never itself computes a feature value - it only
    reads `feature_set.get(condition.field)`, so a missing field is
    always recorded as FAIL with an explicit reason, never guessed."""

    def evaluate(self, rule_set: StrategyRuleSet, *, feature_set: FeatureSet) -> StrategyScanResult:
        condition_results = []
        for condition in rule_set.conditions:
            observed_value = feature_set.get(condition.field)
            if observed_value is None:
                condition_results.append(
                    StrategyConditionResult(
                        condition_name=condition.name,
                        field=condition.field,
                        passed=False,
                        observed_value=None,
                        threshold=condition.threshold,
                        reason=f"feature {condition.field!r} not present in FeatureSet",
                    )
                )
                continue
            comparator_func = _COMPARATOR_FUNCS[condition.comparator]
            passed = comparator_func(observed_value, condition.threshold)
            reason = (
                None
                if passed
                else (
                    f"{condition.field}={observed_value} fails "
                    f"{condition.comparator.value} {condition.threshold}"
                )
            )
            condition_results.append(
                StrategyConditionResult(
                    condition_name=condition.name,
                    field=condition.field,
                    passed=passed,
                    observed_value=observed_value,
                    threshold=condition.threshold,
                    reason=reason,
                )
            )
        return StrategyScanResult(
            strategy_id=rule_set.strategy_id,
            strategy_version=rule_set.strategy_version,
            instrument_symbol=feature_set.instrument_symbol,
            as_of=feature_set.as_of,
            data_source=feature_set.data_source,
            condition_results=condition_results,
        )
