from __future__ import annotations

import pytest

from app.risk.base import RiskDecision, RiskEngine


def test_risk_engine_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        RiskEngine()  # type: ignore[abstract]


def test_risk_decision_defaults_reason_to_none() -> None:
    decision = RiskDecision(approved=True)
    assert decision.reason is None
