"""Market Data Gateway: read-only access to Toss quote/orderbook/trade/candle data.

Confirmed official GET endpoints only:
`/api/v1/prices`, `/api/v1/orderbook`, `/api/v1/trades`,
`/api/v1/price-limits`, `/api/v1/candles`, `/api/v1/stocks`. This
adapter is REST-polling only.

WebSocket status (see docs/architecture/0007-toss-api-integration.md):
    Capability:     OFFICIAL_MARKETING_CONFIRMED
    Protocol:       NOT_VERIFIED
    Implementation: DEFERRED

The official Toss Securities Open API introduction states both REST
and WebSocket are offered, but no WebSocket URL, auth method,
subscribe/unsubscribe protocol, message envelope, heartbeat, or
reconnect policy has been confirmed. No WebSocket client, URL, or
message schema is defined anywhere in this codebase - inventing one
would be exactly the kind of unconfirmed-contract guess this phase
forbids. A `StreamingMarketDataProvider`-shaped interface can be added
once a real protocol document is available to verify against.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

from app.core.exceptions import DataValidationError
from app.toss.client import TossResponseEnvelope, TossRestClient
from app.toss.conversions import parse_timestamp, to_decimal
from app.toss.dto import (
    CandlesResponseDto,
    OrderbookLevelDto,
    OrderbookResponseDto,
    PricesResponseDto,
    RawEnvelopeDto,
    TradesResponseDto,
)
from app.toss.models import (
    TOSS_SOURCE_NAME,
    Candle,
    CandleSeries,
    OrderBookLevel,
    OrderBookSnapshot,
    Quote,
    RecordMetadata,
    TradeTick,
    UnparsedRecord,
)
from app.toss.rate_limit import RateLimitGroup

MIN_CANDLE_COUNT = 1
MAX_CANDLE_COUNT = 200


class CandleInterval(StrEnum):
    ONE_MINUTE = "1m"
    ONE_DAY = "1d"


class MarketDataAdapter:
    def __init__(
        self,
        client: TossRestClient,
        *,
        capture_raw_payload: bool = False,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._capture_raw_payload = capture_raw_payload
        self._clock = clock

    def get_price(self, symbol: str) -> Quote:
        envelope = self._client.get(
            "/api/v1/prices", params={"symbol": symbol}, group=RateLimitGroup.STOCK
        )
        dto = PricesResponseDto.model_validate(envelope.payload)
        if not dto.result:
            raise DataValidationError(f"No price result returned for symbol={symbol!r}")
        item = dto.result[0]
        event_time = parse_timestamp(item.timestamp, field="timestamp")
        return Quote(
            metadata=self._metadata(envelope, event_time=event_time),
            symbol=item.symbol,
            last_price=to_decimal(item.lastPrice, field="lastPrice"),
            currency=item.currency,
        )

    def get_orderbook(self, symbol: str) -> OrderBookSnapshot:
        envelope = self._client.get(
            "/api/v1/orderbook", params={"symbol": symbol}, group=RateLimitGroup.STOCK
        )
        dto = OrderbookResponseDto.model_validate(envelope.payload)
        result = dto.result
        event_time = parse_timestamp(result.timestamp, field="timestamp")
        return OrderBookSnapshot(
            metadata=self._metadata(envelope, event_time=event_time),
            symbol=symbol,
            currency=result.currency,
            asks=[self._level(level) for level in result.asks],
            bids=[self._level(level) for level in result.bids],
        )

    @staticmethod
    def _level(level: OrderbookLevelDto) -> OrderBookLevel:
        return OrderBookLevel(
            price=to_decimal(level.price, field="price"),
            volume=to_decimal(level.volume, field="volume"),
        )

    def get_trades(self, symbol: str) -> list[TradeTick]:
        envelope = self._client.get(
            "/api/v1/trades", params={"symbol": symbol}, group=RateLimitGroup.STOCK
        )
        dto = TradesResponseDto.model_validate(envelope.payload)
        return [
            TradeTick(
                metadata=self._metadata(
                    envelope, event_time=parse_timestamp(item.timestamp, field="timestamp")
                ),
                symbol=symbol,
                price=to_decimal(item.price, field="price"),
                volume=to_decimal(item.volume, field="volume"),
                currency=item.currency,
            )
            for item in dto.result
        ]

    def get_candles(
        self,
        symbol: str,
        interval: CandleInterval,
        count: int,
        *,
        before: str | None = None,
    ) -> CandleSeries:
        if not MIN_CANDLE_COUNT <= count <= MAX_CANDLE_COUNT:
            raise ValueError(
                f"count must be between {MIN_CANDLE_COUNT} and {MAX_CANDLE_COUNT}, got {count}"
            )

        params: dict[str, str | int] = {
            "symbol": symbol,
            "interval": interval.value,
            "count": count,
        }
        if before is not None:
            params["before"] = before

        envelope = self._client.get("/api/v1/candles", params=params, group=RateLimitGroup.STOCK)
        dto = CandlesResponseDto.model_validate(envelope.payload)
        candles = [
            Candle(
                timestamp=parse_timestamp(item.timestamp, field="timestamp"),
                open_price=to_decimal(item.openPrice, field="openPrice"),
                high_price=to_decimal(item.highPrice, field="highPrice"),
                low_price=to_decimal(item.lowPrice, field="lowPrice"),
                close_price=to_decimal(item.closePrice, field="closePrice"),
                volume=to_decimal(item.volume, field="volume"),
                currency=item.currency,
            )
            for item in dto.result.candles
        ]
        return CandleSeries(
            metadata=self._metadata(envelope, event_time=None),
            symbol=symbol,
            interval=interval.value,
            candles=candles,
            next_before=dto.result.nextBefore,
        )

    def get_price_limits(self, symbol: str) -> UnparsedRecord:
        return self._get_unparsed(
            "/api/v1/price-limits", params={"symbol": symbol}, group=RateLimitGroup.STOCK
        )

    def get_stocks(self, **params: str) -> UnparsedRecord:
        return self._get_unparsed(
            "/api/v1/stocks", params=params or None, group=RateLimitGroup.STOCK
        )

    def _get_unparsed(
        self, path: str, *, params: dict[str, str] | None, group: RateLimitGroup
    ) -> UnparsedRecord:
        envelope = self._client.get(path, params=params, group=group)
        dto = RawEnvelopeDto.model_validate(envelope.payload)
        return UnparsedRecord(metadata=self._metadata(envelope, event_time=None), result=dto.result)

    def _metadata(
        self, envelope: TossResponseEnvelope, *, event_time: datetime | None
    ) -> RecordMetadata:
        return RecordMetadata(
            source=TOSS_SOURCE_NAME,
            event_time=event_time,
            available_at=envelope.received_at,
            ingested_at=envelope.received_at,
            raw_payload=envelope.payload if self._capture_raw_payload else None,
        )
