"""`SignalInput`: the structured combination of AI Context, the Quant
Model's calibrated probability, and Market Regime for one
`(instrument, as_of)` - pure data, no database import.

**This is not an order and nothing here generates one.** `SignalInput`
carries evidence, not a decision - see `app.signals.engine`'s module
docstring and ADR 0011. `app.brokers`/`app.execution` remain
interface-only (Phase 00) regardless of what a `SignalInput` contains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.ai_context.schema import AIContextResult
from app.regime.classifier import RegimeAssessment


@dataclass(frozen=True)
class QuantProbability:
    model_name: str
    model_version: str
    feature_schema_version: str
    label_definition_version: str
    probability: float
    as_of: datetime


@dataclass(frozen=True)
class SignalInput:
    instrument_id: int
    symbol: str
    as_of: datetime
    generated_at: datetime
    ai_context: list[AIContextResult] = field(default_factory=list)
    quant_probability: QuantProbability | None = None
    regime: RegimeAssessment | None = None

    @property
    def has_ai_context(self) -> bool:
        return len(self.ai_context) > 0

    @property
    def has_quant_probability(self) -> bool:
        return self.quant_probability is not None

    @property
    def has_regime(self) -> bool:
        return self.regime is not None


def build_signal_input(
    *,
    instrument_id: int,
    symbol: str,
    as_of: datetime,
    generated_at: datetime,
    ai_context: list[AIContextResult] | None = None,
    quant_probability: QuantProbability | None = None,
    regime: RegimeAssessment | None = None,
) -> SignalInput:
    """A missing input (no AI Context items, no quant probability, no
    regime) is represented as an empty list / `None` - never a
    fabricated placeholder value - so a downstream consumer can tell
    "this input wasn't available" from "this input said X"."""
    return SignalInput(
        instrument_id=instrument_id,
        symbol=symbol,
        as_of=as_of,
        generated_at=generated_at,
        ai_context=ai_context or [],
        quant_probability=quant_probability,
        regime=regime,
    )
