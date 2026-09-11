# Strategy Research Lab: usage guide

The Research Lab turns a strategy idea (from TradingView, a paper, or
anywhere else) into a reproducible `StrategySpec` record stored in the
Strategy Registry. It is a research/documentation tool - it never
places an order and never auto-promotes a strategy's status. See
`docs/architecture/0006-strategy-research-lab.md` for the design
rationale.

## Quick start

```python
from datetime import date

from app.research.models import (
    PineValidationAssumptions,
    StrategySource,
    StrategySpec,
    StrategyStatus,
)
from app.research.registry import StrategyRegistry

# 1. Record a fresh idea at the "research" stage - no validation data yet.
spec = StrategySpec(
    strategy_id="STR-MY-001",
    name="My new idea",
    version="0.1.0",
    source=StrategySource.MANUAL,
    hypothesis="Symbols above their 200-day MA with rising volume outperform.",
    universe=["KOSPI:005930"],
    timeframe="1D",
    entry_rules=["Close above 200-day MA and volume > 20-day avg volume"],
    exit_rules=["Close crosses below 200-day MA"],
    risk_assumptions=["Max 5% of paper-trading capital per position"],
    status=StrategyStatus.RESEARCH,
)

registry = StrategyRegistry()  # defaults to research/strategies/
registry.save(spec)

# 2. After running (and manually copying) a Pine Script backtest on
#    TradingView, record the assumptions needed to reproduce it, and
#    save a new version at pine_validated.
validated = spec.model_copy(
    update={
        "version": "0.2.0",
        "status": StrategyStatus.PINE_VALIDATED,
        "pine_validation": PineValidationAssumptions(
            test_period_start=date(2022, 1, 1),
            test_period_end=date(2023, 12, 31),
            symbols=["KOSPI:005930"],
            timeframe="1D",
            fees_pct=0.015,
            slippage_pct=0.05,
            notes="Copied by hand from TradingView Strategy Tester on 2026-09-11.",
        ),
    }
)
registry.save(validated)

# 3. Reload later (e.g. in a Python backtest driver, once one exists)
reloaded = registry.load_latest("STR-MY-001")
assert reloaded == validated
```

## Status ladder

```
research -> pine_validated -> python_validated -> paper -> approved -> retired
   \_____________________________________________________________/
                    (an idea can also be retired directly)
```

- **research**: an idea with a stated hypothesis, no validation yet.
- **pine_validated**: a Pine Script backtest was run (see
  `docs/research/tradingview-mcp-health-check.md` for checking
  TradingView MCP connectivity first) and its assumptions
  (`pine_validation`) are recorded. Treat this as a fast first-pass
  filter only - never as approval.
- **python_validated**: reproduced (or re-tested) in a Python
  backtest. No backtest engine implementation exists yet (Phase 01 is
  research-lab-only, see ADR 0001) - this status is available for when
  one does.
- **paper**: running in paper trading. No paper broker implementation
  exists yet either (same reason).
- **approved**: cleared for the next stage by a human decision. This
  status still does not place any real order - there is no live
  broker/execution code in this repository (ADR 0004/0006).
- **retired**: no longer pursued.

**Every status beyond `research`/`retired` requires a populated
`pine_validation` block** - `StrategySpec` will refuse to validate
otherwise. This is enforced in code
(`app/research/models.py::_validated_statuses_need_pine_assumptions`),
not just documented.

## Rules this Lab enforces (and what stays a human's job)
- **Status changes are always an explicit save**, never a side effect
  of a TradingView MCP call or any other automation. Claude may draft
  a status change for a human to review and save, but nothing in this
  codebase performs one automatically.
- **`StrategyRegistry.save()` is append-only by default** - saving a
  `(strategy_id, version)` that already exists raises
  `StrategyVersionExistsError` unless `overwrite=True` is passed
  explicitly. Bump `version` for a new research iteration instead of
  overwriting history.
- **Nothing here talks to a broker.** `app.research` depends only on
  `app.core` (see its `__init__.py`) - there is no import path from a
  `StrategySpec` to an order.

## File layout

```
app/research/
    models.py            StrategySpec, StrategyStatus, StrategySource, PineValidationAssumptions
    registry.py           StrategyRegistry (file-based, JSON, versioned)
    tradingview_mcp.py     Isolated, non-blocking TradingView MCP health check

research/strategies/
    <strategy_id>/
        <version>.json     One StrategySpec per (strategy_id, version)

docs/research/
    tradingview-mcp-health-check.md    Manual connectivity-check procedure
    strategy-research-lab-guide.md      This file

docs/architecture/
    0006-strategy-research-lab.md       Design rationale (ADR)

tests/research/
    test_models.py         StrategySpec/PineValidationAssumptions validation rules
    test_registry.py        Save/load/overwrite/list round-trip behavior
    test_tradingview_mcp.py  Health-check status mapping, never raises
    test_isolation.py        Registry works while TradingView MCP is simulated "down"
```
