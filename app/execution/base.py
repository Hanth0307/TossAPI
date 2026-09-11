"""Order execution orchestration interface.

An implementation must run every order through a `RiskEngine` before
calling `BrokerBase.place_order`, and must use
`app.adapters.http_client.NO_RETRY_POLICY` for that broker call so a
network hiccup can never cause an automatic duplicate submission.
No such implementation exists in Phase 00.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.brokers.base import OrderRequest, OrderResult


class ExecutionEngine(ABC):
    """Coordinates a risk check and broker submission for one order."""

    @abstractmethod
    def submit(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError
