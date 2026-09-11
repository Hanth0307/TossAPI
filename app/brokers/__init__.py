"""Broker adapter interfaces (paper and, eventually, live).

Depends on `app.core` and `app.adapters`. No adapter here places a
real order - `BrokerBase` defines the interface only. A paper broker
implementation belongs to a later phase.
"""
