"""Signal Engine (Phase 05): structures `app.ai_context`, `app.models`
(Quant Model), and `app.regime` (Market Regime) into one `SignalInput`
per `(instrument, as_of)` - see
docs/architecture/0011-ai-context-quant-regime-signal-engine.md.

Depends on `app.core`, `app.db`, `app.ai_context`, `app.models`, and
`app.regime`. `schema.py` is pure logic (no database import) -
`engine.py` is the sole place this package touches `app.db`, and every
fetch it makes goes through an `as_of`-gated repository method or an
`as_of`-gated provider (`RegimeProvider`), so a `SignalInput` is
exactly as point-in-time-safe as those two are.

**Nothing in this package generates an order.** A `SignalInput` is
evidence for a later phase (backtesting, and eventually strategy/
execution) to consume - `app.brokers`/`app.execution` remain
interface-only (Phase 00) regardless of what any field here says. This
is the same guarantee `app.scanners.candidate.Candidate` makes for the
Scanner layer (Phase 04), extended to the AI/quant layer.
"""
