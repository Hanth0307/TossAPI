"""Risk engine interface: gates every order before it reaches a broker.

Depends on `app.core` and `app.brokers` (for `OrderRequest`). No risk
rules (position limits, drawdown caps, exposure limits, ...) are
implemented in Phase 00.
"""
