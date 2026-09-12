"""Order records - our own actions, never written by any order-placing
code (there is none in this codebase - see ADR 0004/0006/0007). These
tables exist so a future paper/live broker has somewhere to record
what it did, idempotently.

`paper_orders` is idempotent on `client_order_id` - mirroring
`app.brokers.base.OrderRequest.client_order_id` from Phase 00, so a
retried submission is recorded once. `broker_orders` is idempotent on
`(broker_order_id, source)`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.db.repositories._idempotent_insert import get_or_insert
from app.db.schema import broker_orders, paper_orders


@dataclass(frozen=True)
class PaperOrderRow:
    client_order_id: str
    instrument_id: int
    side: str
    order_type: str
    quantity: Decimal
    limit_price: Decimal | None
    status: str
    submitted_at: datetime
    updated_at: datetime


class PaperOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record_submission(
        self,
        *,
        client_order_id: str,
        instrument_id: int,
        side: str,
        order_type: str,
        quantity: Decimal,
        limit_price: Decimal | None = None,
        status: str = "submitted",
        raw_payload: Mapping[str, Any] | None = None,
    ) -> tuple[int, bool]:
        return get_or_insert(
            self._session,
            paper_orders,
            lookup={"client_order_id": client_order_id},
            values={
                "client_order_id": client_order_id,
                "instrument_id": instrument_id,
                "side": side,
                "order_type": order_type,
                "quantity": quantity,
                "limit_price": limit_price,
                "status": status,
                "raw_payload": raw_payload,
            },
        )

    def update_status(self, client_order_id: str, status: str) -> None:
        self._session.execute(
            update(paper_orders)
            .where(paper_orders.c.client_order_id == client_order_id)
            .values(status=status, updated_at=func.now())
        )

    def get_by_client_order_id(self, client_order_id: str) -> PaperOrderRow | None:
        stmt = select(paper_orders).where(paper_orders.c.client_order_id == client_order_id)
        row = self._session.execute(stmt).mappings().one_or_none()
        if row is None:
            return None
        return PaperOrderRow(**{f: row[f] for f in PaperOrderRow.__dataclass_fields__})


class BrokerOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record_order(
        self,
        *,
        broker_order_id: str,
        source: str,
        status: str,
        client_order_id: str | None = None,
        instrument_id: int | None = None,
        side: str | None = None,
        order_type: str | None = None,
        quantity: Decimal | None = None,
        limit_price: Decimal | None = None,
        submitted_at: datetime | None = None,
        raw_payload: Mapping[str, Any] | None = None,
    ) -> tuple[int, bool]:
        return get_or_insert(
            self._session,
            broker_orders,
            lookup={"broker_order_id": broker_order_id, "source": source},
            values={
                "broker_order_id": broker_order_id,
                "source": source,
                "client_order_id": client_order_id,
                "instrument_id": instrument_id,
                "side": side,
                "order_type": order_type,
                "quantity": quantity,
                "limit_price": limit_price,
                "status": status,
                "submitted_at": submitted_at,
                "raw_payload": raw_payload,
            },
        )
