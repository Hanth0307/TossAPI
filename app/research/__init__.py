"""Strategy Research Lab.

Depends on `app.core` only - `app.research` has no import edge to
`app.data`, `app.brokers`, `app.risk`, or `app.execution`. A
TradingView MCP outage or a Strategy Registry bug here must never
affect the live data/order path (Phase 01 defines no such path yet;
see docs/architecture/0006-strategy-research-lab.md).

This package turns strategy ideas researched on TradingView (or
anywhere else) into a reproducible `StrategySpec` record
(`models.py`), stored in a versioned, file-based Strategy Registry
(`registry.py`). `tradingview_mcp.py` is an isolated, non-blocking
health check for the TradingView MCP connection used during that
research - it is never a dependency of anything outside this package.

Nothing in this package places an order, runs a live strategy, or
auto-promotes a `StrategySpec`'s status. Status changes are always an
explicit, human-made edit to a saved spec.
"""
