"""`StrategySpec`: the reproducible record of one strategy research artifact.

A `StrategySpec` is documentation, not executable code. It exists so a
person (or Claude, under human direction) can re-run the same
hypothesis test - on TradingView Pine Script, in a Python backtest, or
in paper trading - and get the same setup every time. Saving/loading
one is handled by `app.research.registry.StrategyRegistry`; nothing
here calls a broker, and nothing here auto-approves a strategy.

Status ladder (`StrategyStatus`): research -> pine_validated ->
python_validated -> paper -> approved -> retired. Pine Script is
treated as a fast, cheap first-pass filter (see
docs/architecture/0006-strategy-research-lab.md) - so any status past
`research` (except `retired`, which a strategy can reach directly by
being rejected during research) must carry recorded
`pine_validation` assumptions, otherwise nobody could reproduce the
numbers that justified the promotion.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrategyStatus(StrEnum):
    RESEARCH = "research"
    PINE_VALIDATED = "pine_validated"
    PYTHON_VALIDATED = "python_validated"
    PAPER = "paper"
    APPROVED = "approved"
    RETIRED = "retired"


class StrategySource(StrEnum):
    TRADINGVIEW_PINE = "tradingview_pine"
    PYTHON_BACKTEST = "python_backtest"
    EXTERNAL = "external"
    MANUAL = "manual"


# Statuses that claim a Pine Script validation pass has happened, and
# therefore must carry the assumptions needed to reproduce it.
_STATUSES_REQUIRING_PINE_VALIDATION = frozenset(
    {
        StrategyStatus.PINE_VALIDATED,
        StrategyStatus.PYTHON_VALIDATED,
        StrategyStatus.PAPER,
        StrategyStatus.APPROVED,
    }
)


class PineValidationAssumptions(BaseModel):
    """Everything needed to manually reproduce a Pine Script result.

    Pine results are copied by hand from the TradingView UI (see
    docs/research/tradingview-mcp-health-check.md) - without these
    fields recorded alongside the copied numbers, nobody could tell
    what period/symbol/cost assumptions produced them.
    """

    model_config = ConfigDict(extra="forbid")

    test_period_start: date
    test_period_end: date
    symbols: list[str]
    timeframe: str
    fees_pct: float = Field(ge=0)
    slippage_pct: float = Field(ge=0)
    notes: str | None = None

    @field_validator("symbols")
    @classmethod
    def _non_empty_symbols(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("symbols must not be empty")
        return value

    @model_validator(mode="after")
    def _period_is_ordered(self) -> PineValidationAssumptions:
        if self.test_period_end < self.test_period_start:
            raise ValueError("test_period_end must not be before test_period_start")
        return self


class StrategySpec(BaseModel):
    """One versioned strategy research record."""

    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    name: str
    version: str
    source: StrategySource
    hypothesis: str
    universe: list[str]
    timeframe: str
    entry_rules: list[str]
    exit_rules: list[str]
    risk_assumptions: list[str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: StrategyStatus = StrategyStatus.RESEARCH

    # Required once `status` claims a Pine validation pass - see
    # `_STATUSES_REQUIRING_PINE_VALIDATION` above.
    pine_validation: PineValidationAssumptions | None = None

    @field_validator("strategy_id", "name", "version", "hypothesis", "timeframe")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("universe", "entry_rules", "exit_rules", "risk_assumptions")
    @classmethod
    def _non_empty_list(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def _validated_statuses_need_pine_assumptions(self) -> StrategySpec:
        if self.status in _STATUSES_REQUIRING_PINE_VALIDATION and self.pine_validation is None:
            raise ValueError(
                f"status={self.status!r} requires pine_validation to be recorded "
                "(test period, symbols, timeframe, fees, slippage) for reproducibility"
            )
        return self
