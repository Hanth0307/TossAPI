# TradingView MCP health check procedure

## Purpose
Answer one question before starting or resuming strategy research:
**is the TradingView MCP tool reachable right now?** This is a
manual, researcher-run check - it is not wired into any automated
pipeline, and its result never gates anything outside strategy
research itself (see
`docs/architecture/0006-strategy-research-lab.md`).

## When to run this
- Before starting a new Pine-validation pass on a `StrategySpec`.
- Whenever a TradingView MCP tool call unexpectedly fails or times out
  mid-session, to confirm whether the tool itself is down versus one
  bad call.
- It is **not** a prerequisite for anything else in this repository:
  `pytest`, the Strategy Registry, and every other module work with
  TradingView MCP completely absent (see
  `tests/research/test_isolation.py`).

## Procedure
1. **List available MCP tools/servers** in the current Claude Code
   session (e.g. via the session's tool/server listing) and look for a
   TradingView-named MCP server or tool.
2. **If present**, invoke one lightweight, read-only call - e.g. fetch
   the latest bar/quote for a well-known symbol - and confirm a valid
   response comes back within a reasonable time (a few seconds).
3. **Record the result** using
   `app.research.tradingview_mcp.check_tradingview_mcp_health()`,
   passing a `probe` callable that wraps step 2 (returns `True` on a
   valid response, `False` on an explicit "not connected" response,
   and lets exceptions propagate out of the probe - the health check
   catches them and reports `ERROR`).
4. **If the server is absent, the call fails, or it times out**, the
   result is `UNAVAILABLE` or `ERROR` - note it in your research notes
   and move on. Do not block other work on it.

```python
from app.research.tradingview_mcp import check_tradingview_mcp_health

def probe() -> bool:
    # Replace with an actual lightweight TradingView MCP call once one
    # is wired into this environment; must return True/False and may
    # raise on failure - check_tradingview_mcp_health() will not let
    # that exception escape.
    ...

result = check_tradingview_mcp_health(probe=probe)
print(result.status, result.checked_at, result.detail)
```

## Interpreting the result
| Status | Meaning |
|---|---|
| `connected` | The probe call succeeded - TradingView MCP is usable right now. |
| `unavailable` | The probe ran and explicitly reported "not connected" (e.g. an auth/handshake failure). |
| `error` | The probe raised an exception (network error, timeout, unexpected response, ...). The exception is logged (`tradingview_mcp.health_check_failed`) and never propagates. |
| `not_configured` | No probe was supplied - no TradingView MCP integration is wired into this check yet. This is the expected result until a real probe is implemented for the environment running the check. |

## Isolation guarantee
This check must never gate:
- The core `pytest` suite (`make test`) - none of it depends on
  TradingView MCP being reachable.
- `app.data`, `app.brokers`, `app.risk`, `app.execution` - none of
  them import `app.research.tradingview_mcp`.
- Strategy Registry reads/writes (`app.research.registry`) - saving
  and loading a `StrategySpec` never calls this module.

If TradingView MCP is down for an extended period, continue research
through whatever channel is available (manually copying results from
the TradingView UI, or skipping straight to a Python backtest) and
record that in the `StrategySpec`'s `pine_validation.notes` field once
Pine validation does happen.

## What this check must never be used for
- Auto-approving a strategy. A `connected` result says nothing about
  whether any particular strategy is good - it only says the tool is
  reachable.
- Feeding a live order path. There is no such path in this repository
  to feed (see ADR 0004/0006) - do not add one behind this check.
