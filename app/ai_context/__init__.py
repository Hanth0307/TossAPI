"""AI Context (Phase 05): turns one news/disclosure item into a fixed,
structured classification - entity linking, event type, direct/
indirect impact, one-off/structural impact, novelty/duplicate
clustering, source reliability, and a per-horizon (1d/5d/10d/long-term)
directional assessment. See docs/architecture/0011-ai-context-quant-regime-signal-engine.md.

Depends on `app.core` and `app.db` only. The LLM call itself
(`claude_extractor.py`) is isolated exactly like `app.research.
tradingview_mcp` isolates TradingView MCP: any failure is caught and
turned into an explicit `unknown` result (`schema.AIContextResult`),
never raised into a caller and never papered over with a guessed
value. `mock_extractor.py` provides a deterministic, network-free
double with the same contract, for tests and offline use.

**This package never computes a sentiment/trading score.** Its output
is a structured classification only - `app.signals` (Phase 05) is
where AI Context, the Quant Model's probability, and Market Regime are
combined, and even there, no order is generated.
"""
