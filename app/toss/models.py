"""Normalized domain models returned by `MarketDataAdapter` / `PortfolioReadAdapter`.

Separate from the raw DTOs (`app/toss/dto.py`) by design: if a Toss
response field is ever renamed, only `market_data.py`/`portfolio.py`
need to change - nothing downstream that consumes these models does.

Every record carries `RecordMetadata` so provenance is never lost:
`source` (always `"toss_openapi"`), `event_time` (when the market
event happened, per the response's own timestamp - `None` where no
confirmed timestamp field exists), `available_at`/`ingested_at` (when
*our* client observed the response; equal to each other in Phase 02
since there is no separate ingestion pipeline yet - see ADR 0007), and
an optional `raw_payload` for debug/audit use (see
`capture_raw_payload` on the adapters).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

TOSS_SOURCE_NAME = "toss_openapi"


@dataclass(frozen=True)
class RecordMetadata:
    source: str
    event_time: datetime | None
    available_at: datetime
    ingested_at: datetime
    raw_payload: Any | None = None


@dataclass(frozen=True)
class Quote:
    metadata: RecordMetadata
    symbol: str
    last_price: Decimal
    currency: str


@dataclass(frozen=True)
class OrderBookLevel:
    price: Decimal
    volume: Decimal


@dataclass(frozen=True)
class OrderBookSnapshot:
    metadata: RecordMetadata
    symbol: str
    currency: str
    asks: list[OrderBookLevel] = field(default_factory=list)
    bids: list[OrderBookLevel] = field(default_factory=list)


@dataclass(frozen=True)
class TradeTick:
    metadata: RecordMetadata
    symbol: str
    price: Decimal
    volume: Decimal
    currency: str


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    currency: str


@dataclass(frozen=True)
class CandleSeries:
    metadata: RecordMetadata
    symbol: str
    interval: str
    candles: list[Candle]
    next_before: str | None


@dataclass(frozen=True)
class UnparsedRecord:
    """Wraps a response whose field-level schema is not yet confirmed.

    Used for every Phase 02 endpoint that did not come with an
    official JSON example (price-limits, stocks, accounts, holdings,
    orders, order detail, buying-power, sellable-quantity,
    commissions). `result` is exactly the parsed `result` value from
    the response envelope, unmodified - callers needing a specific
    field must read it from here until the schema is confirmed and a
    dedicated DTO/model is added.
    """

    metadata: RecordMetadata
    result: Any
