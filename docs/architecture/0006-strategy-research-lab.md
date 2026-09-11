# ADR 0006: Strategy Research Lab (Phase 01)

## Status
Accepted (Phase 01)

## Context
Strategy ideas need somewhere to live between "someone had a hypothesis
on TradingView" and "a reviewed, reproducible research record exists."
TradingView (via Pine Script, potentially driven through a TradingView
MCP tool) is a fast, cheap way to sanity-check an idea - but its output
must never be mistaken for a validated, tradeable strategy: Pine
backtests use TradingView's own execution/fee/slippage model, run on
whatever chart settings were open at the time, and are easy to
p-hack by eye. The project also has no live order-placing code at all
(see ADR 0004, `app/brokers`, `app/execution`), so nothing here can
plug straight into real trading regardless.

## Decision

### `StrategySpec` and the status ladder
`app.research.models.StrategySpec` (a pydantic model, see ADR 0002 for
why pydantic is the project's validation library of choice) is the
single reproducible record of one strategy research artifact:
`strategy_id`, `name`, `version`, `source`, `hypothesis`, `universe`,
`timeframe`, `entry_rules`, `exit_rules`, `risk_assumptions`,
`created_at`, `status`.

`status` (`StrategyStatus`) is a strict ladder:
`research -> pine_validated -> python_validated -> paper -> approved
-> retired`. A spec can also go `research -> retired` directly (an
idea rejected before any validation). Any status other than
`research`/`retired` requires a populated `pine_validation` block
(`PineValidationAssumptions`: `test_period_start`, `test_period_end`,
`symbols`, `timeframe`, `fees_pct`, `slippage_pct`, `notes`) - enforced
by a pydantic model validator, not just a docstring. This directly
encodes two of the requirements for this phase:

- **Pine results must be reproducible by hand.** Because TradingView
  MCP output is currently copied into a spec manually (see the health
  check doc below), the assumptions that produced a Pine number have
  to travel with it or the number is meaningless six months later.
- **TradingView output is never auto-approved.** There is no method on
  `StrategyRegistry` or anywhere else that reads a Pine result and
  bumps `status` for you. A human (or Claude acting under explicit
  human direction, once) edits a `StrategySpec` and re-saves it - that
  is the only way `status` changes. `app.research` has no code path
  that touches an order, a broker, or `app.execution` at all.

`source` (`StrategySource`) records where an idea came from:
`tradingview_pine`, `python_backtest`, `external`, `manual`. The
sample strategy `STR-EXT-001` ("External Trend Join Long") uses
`external` and is registered at `status=research` only - see
`research/strategies/STR-EXT-001/0.1.0.json`. Its `entry_rules` /
`exit_rules` are explicitly marked `PLACEHOLDER` because the original
Pine source has not actually been reviewed; nothing in this repository
invents specific indicator parameters on its behalf.

### Strategy Registry storage
`app.research.registry.StrategyRegistry` stores each
`(strategy_id, version)` as one JSON file under
`research/strategies/<strategy_id>/<version>.json` - plain,
diffable files reviewable like any other change, no database
dependency for this phase (a Postgres-backed registry can replace this
later, per ADR 0001/0005, behind the same four methods:
`save`/`load`/`load_latest`/`list_versions`). Saving is append-only by
default (`StrategyVersionExistsError` on a duplicate version) so a
past research result can't be silently rewritten out from under
anyone; `overwrite=True` is available for the rare deliberate
correction.

### TradingView MCP isolation
`app.research.tradingview_mcp.check_tradingview_mcp_health()` answers
"is TradingView MCP reachable" without ever raising - any exception
from the supplied `Probe` becomes an `ERROR` status result, and no
probe at all is a normal `NOT_CONFIGURED` result. This module is a
dependency of nothing else in the codebase: `app.research.models` and
`app.research.registry` do not import it, and neither does anything
under `app.data`, `app.brokers`, `app.risk`, or `app.execution`. A
TradingView MCP outage can therefore never break the Strategy Registry
or (once they exist) the real data/order path - it can only affect the
one health-check call a researcher makes by hand. See
`docs/research/tradingview-mcp-health-check.md` for the manual
procedure, and `tests/research/test_isolation.py` for the regression
test proving this dependency separation.

## Consequences
- A strategy can be fully researched, Pine-validated, and Python-
  validated with zero TradingView MCP or broker code running - the
  registry only ever reads/writes JSON.
- Promoting a strategy's status is a deliberate, auditable git diff on
  a JSON file, not a side effect of any automated pipeline.
- Nothing added in this phase changes `app.brokers`/`app.execution`;
  those remain interface-only per ADR 0001, so "approved" here still
  cannot place a real order - there is no code for it to call.
- If a real TradingView MCP client library becomes available later,
  wiring it in is adding one `Probe` implementation - the health-check
  contract (`TradingViewMcpHealthResult`) does not need to change.
