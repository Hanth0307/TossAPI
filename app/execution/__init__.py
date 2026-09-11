"""Order execution orchestration interface.

Depends on `app.core`, `app.brokers`, and `app.risk`. No order is
ever submitted by code in Phase 00 - `ExecutionEngine` defines the
interface only.
"""
