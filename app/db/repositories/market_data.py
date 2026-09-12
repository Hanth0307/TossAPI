"""Instruments, market bars, trade ticks, orderbook snapshots.

Every `get_*_as_of` method requires `as_of` and filters
`available_at <= as_of` - see `app.db.repositories` module docstring
and docs/architecture/0008-data-platform.md.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.schema import instruments, market_bars, orderbook_snapshots, trade_ticks
from app.db.upsert import upsert_event_rows


@dataclass(frozen=True)
class InstrumentRow:
    id: int
    exchange: str
    symbol: str
    name: str | None
    currency: str | None
    source: str


@dataclass(frozen=True)
class MarketBarRow:
    instrument_id: int
    timeframe: str
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    currency: str | None
    source: str


@dataclass(frozen=True)
class TradeTickRow:
    instrument_id: int
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    price: Decimal
    volume: Decimal
    currency: str | None
    source: str


@dataclass(frozen=True)
class OrderBookSnapshotRow:
    instrument_id: int
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    currency: str | None
    asks: list[dict[str, Any]]
    bids: list[dict[str, Any]]
    source: str


class InstrumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create(
        self,
        *,
        exchange: str,
        symbol: str,
        source: str,
        name: str | None = None,
        currency: str | None = None,
        raw_payload: Any | None = None,
    ) -> InstrumentRow:
        insert_stmt = pg_insert(instruments).values(
            exchange=exchange,
            symbol=symbol,
            name=name,
            currency=currency,
            source=source,
            raw_payload=raw_payload,
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["exchange", "symbol"],
            set_={"updated_at": insert_stmt.excluded.updated_at},
        ).returning(instruments)
        row = self._session.execute(stmt).mappings().one()
        return InstrumentRow(**{f: row[f] for f in InstrumentRow.__dataclass_fields__})

    def get_by_symbol(self, *, exchange: str, symbol: str) -> InstrumentRow | None:
        stmt = select(instruments).where(
            instruments.c.exchange == exchange, instruments.c.symbol == symbol
        )
        row = self._session.execute(stmt).mappings().one_or_none()
        if row is None:
            return None
        return InstrumentRow(**{f: row[f] for f in InstrumentRow.__dataclass_fields__})


class MarketBarRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_bars(self, bars: Sequence[Mapping[str, Any]]) -> int:
        return upsert_event_rows(
            self._session,
            market_bars,
            bars,
            natural_key_columns=["instrument_id", "timeframe", "event_time", "source"],
            update_columns=[
                "open_price",
                "high_price",
                "low_price",
                "close_price",
                "volume",
                "currency",
            ],
        )

    def get_bars_as_of(
        self,
        *,
        instrument_id: int,
        timeframe: str,
        start: datetime,
        end: datetime,
        as_of: datetime,
    ) -> list[MarketBarRow]:
        stmt = (
            select(market_bars)
            .where(
                market_bars.c.instrument_id == instrument_id,
                market_bars.c.timeframe == timeframe,
                market_bars.c.event_time >= start,
                market_bars.c.event_time <= end,
                market_bars.c.available_at <= as_of,
            )
            .order_by(market_bars.c.event_time)
        )
        rows = self._session.execute(stmt).mappings().all()
        return [
            MarketBarRow(**{f: row[f] for f in MarketBarRow.__dataclass_fields__}) for row in rows
        ]


class TradeTickRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_ticks(self, ticks: Sequence[Mapping[str, Any]]) -> int:
        return upsert_event_rows(
            self._session,
            trade_ticks,
            ticks,
            natural_key_columns=["instrument_id", "event_time", "source", "price", "volume"],
            update_columns=[],
            on_conflict="nothing",
        )

    def get_ticks_as_of(
        self, *, instrument_id: int, start: datetime, end: datetime, as_of: datetime
    ) -> list[TradeTickRow]:
        stmt = (
            select(trade_ticks)
            .where(
                trade_ticks.c.instrument_id == instrument_id,
                trade_ticks.c.event_time >= start,
                trade_ticks.c.event_time <= end,
                trade_ticks.c.available_at <= as_of,
            )
            .order_by(trade_ticks.c.event_time)
        )
        rows = self._session.execute(stmt).mappings().all()
        return [
            TradeTickRow(**{f: row[f] for f in TradeTickRow.__dataclass_fields__}) for row in rows
        ]


class OrderbookRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_snapshots(self, snapshots: Sequence[Mapping[str, Any]]) -> int:
        return upsert_event_rows(
            self._session,
            orderbook_snapshots,
            snapshots,
            natural_key_columns=["instrument_id", "event_time", "source"],
            update_columns=["currency", "asks", "bids"],
        )

    def get_latest_as_of(
        self, *, instrument_id: int, as_of: datetime
    ) -> OrderBookSnapshotRow | None:
        stmt = (
            select(orderbook_snapshots)
            .where(
                orderbook_snapshots.c.instrument_id == instrument_id,
                orderbook_snapshots.c.available_at <= as_of,
            )
            .order_by(orderbook_snapshots.c.event_time.desc())
            .limit(1)
        )
        row = self._session.execute(stmt).mappings().one_or_none()
        if row is None:
            return None
        return OrderBookSnapshotRow(
            **{f: row[f] for f in OrderBookSnapshotRow.__dataclass_fields__}
        )
