"""Broker adapter interface.

Phase 00 defines the interface only - no adapter (paper or live)
places real orders here. `place_order` and `cancel_order` are order-
mutating by nature: any future implementation must call them through
`app.adapters.http_client.NO_RETRY_POLICY` (never the default,
auto-retrying policy) and use `OrderRequest.client_order_id` for
idempotency, to avoid submitting a duplicate order after a timeout.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    limit_price: Decimal | None = None
    # Required by any real implementation to make order submission
    # idempotent - a retried/resubmitted request with the same
    # client_order_id must not create a second order at the broker.
    client_order_id: str | None = None


@dataclass(frozen=True)
class OrderResult:
    broker_order_id: str
    status: str
    raw_response: dict[str, Any]


class BrokerBase(ABC):
    """Common interface every broker adapter (paper, live) must implement."""

    @abstractmethod
    def get_account_balance(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError
