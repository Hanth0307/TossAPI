from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.research.models import (
    PineValidationAssumptions,
    StrategySource,
    StrategySpec,
    StrategyStatus,
)


def _base_kwargs() -> dict[str, Any]:
    return dict(
        strategy_id="STR-TEST-001",
        name="Test strategy",
        version="0.1.0",
        source=StrategySource.MANUAL,
        hypothesis="Placeholder hypothesis for testing.",
        universe=["KOSPI:005930"],
        timeframe="1D",
        entry_rules=["rule"],
        exit_rules=["rule"],
        risk_assumptions=["assumption"],
    )


def _assumptions(**overrides: Any) -> PineValidationAssumptions:
    defaults: dict[str, Any] = dict(
        test_period_start=date(2023, 1, 1),
        test_period_end=date(2023, 12, 31),
        symbols=["KOSPI:005930"],
        timeframe="1D",
        fees_pct=0.015,
        slippage_pct=0.1,
    )
    defaults.update(overrides)
    return PineValidationAssumptions(**defaults)


def test_research_status_does_not_require_pine_validation() -> None:
    spec = StrategySpec(**_base_kwargs(), status=StrategyStatus.RESEARCH)
    assert spec.pine_validation is None
    assert spec.status == StrategyStatus.RESEARCH


def test_retired_status_does_not_require_pine_validation() -> None:
    spec = StrategySpec(**_base_kwargs(), status=StrategyStatus.RETIRED)
    assert spec.pine_validation is None


@pytest.mark.parametrize(
    "status",
    [
        StrategyStatus.PINE_VALIDATED,
        StrategyStatus.PYTHON_VALIDATED,
        StrategyStatus.PAPER,
        StrategyStatus.APPROVED,
    ],
)
def test_validated_statuses_require_pine_validation(status: StrategyStatus) -> None:
    with pytest.raises(ValidationError, match="pine_validation"):
        StrategySpec(**_base_kwargs(), status=status)


@pytest.mark.parametrize(
    "status",
    [
        StrategyStatus.PINE_VALIDATED,
        StrategyStatus.PYTHON_VALIDATED,
        StrategyStatus.PAPER,
        StrategyStatus.APPROVED,
    ],
)
def test_validated_statuses_are_valid_with_pine_validation(status: StrategyStatus) -> None:
    spec = StrategySpec(**_base_kwargs(), status=status, pine_validation=_assumptions())
    assert spec.pine_validation is not None


def test_pine_validation_rejects_inverted_period() -> None:
    with pytest.raises(ValidationError):
        _assumptions(test_period_start=date(2023, 12, 31), test_period_end=date(2023, 1, 1))


def test_pine_validation_rejects_empty_symbols() -> None:
    with pytest.raises(ValidationError):
        _assumptions(symbols=[])


def test_pine_validation_rejects_negative_fees() -> None:
    with pytest.raises(ValidationError):
        _assumptions(fees_pct=-0.01)


@pytest.mark.parametrize("field", ["universe", "entry_rules", "exit_rules", "risk_assumptions"])
def test_empty_lists_are_rejected(field: str) -> None:
    kwargs = _base_kwargs()
    kwargs[field] = []
    with pytest.raises(ValidationError):
        StrategySpec(**kwargs)


def test_blank_strategy_id_is_rejected() -> None:
    kwargs = _base_kwargs()
    kwargs["strategy_id"] = "   "
    with pytest.raises(ValidationError):
        StrategySpec(**kwargs)


def test_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        StrategySpec(**_base_kwargs(), unexpected_field="nope")


def test_default_status_is_research() -> None:
    spec = StrategySpec(**_base_kwargs())
    assert spec.status == StrategyStatus.RESEARCH
