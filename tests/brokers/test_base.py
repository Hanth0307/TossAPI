from __future__ import annotations

import pytest

from app.brokers.base import BrokerBase, OrderRequest, OrderSide, OrderType


def test_broker_base_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        BrokerBase()  # type: ignore[abstract]


def test_order_request_is_immutable() -> None:
    from decimal import Decimal

    order = OrderRequest(
        symbol="005930",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("10"),
        limit_price=Decimal("70000"),
        client_order_id="test-1",
    )
    with pytest.raises(AttributeError):
        order.quantity = Decimal("20")  # type: ignore[misc]
