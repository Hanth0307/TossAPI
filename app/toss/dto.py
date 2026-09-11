"""Raw response DTOs - one-to-one with confirmed official JSON examples.

Every field below was shown verbatim in the official docs provided
for this phase. `extra="ignore"` on every DTO: an undocumented field
Toss adds later must never break parsing of the fields we do know
about - see docs/architecture/0007-toss-api-integration.md.

Endpoints whose response field schema was *not* shown (price-limits,
stocks, accounts, holdings, orders, order detail, buying-power,
sellable-quantity, commissions) have no DTO here on purpose - see
`RawEnvelopeDto` and `app/toss/models.py::UnparsedRecord`. Inventing
field names for them would violate the "never guess an unconfirmed
response field" rule for this phase.

The OAuth token response DTO is **not** here - see
`app/toss/token_parser.py`. Unlike every DTO below, its fields were
never shown in an official example; it lives in its own module,
explicitly marked provisional/unverified, so it cannot be mistaken for
a confirmed schema alongside these.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class PriceDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str
    timestamp: str
    lastPrice: str
    currency: str


class PricesResponseDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: list[PriceDto]


class OrderbookLevelDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    price: str
    volume: str


class OrderbookDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timestamp: str
    currency: str
    asks: list[OrderbookLevelDto]
    bids: list[OrderbookLevelDto]


class OrderbookResponseDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: OrderbookDto


class TradeDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    price: str
    volume: str
    timestamp: str
    currency: str


class TradesResponseDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: list[TradeDto]


class CandleDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timestamp: str
    openPrice: str
    highPrice: str
    lowPrice: str
    closePrice: str
    volume: str
    currency: str


class CandlesResultDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candles: list[CandleDto]
    nextBefore: str | None = None


class CandlesResponseDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: CandlesResultDto


class RawEnvelopeDto(BaseModel):
    """Generic `{"result": ...}` envelope for endpoints with no confirmed
    field-level schema. The envelope shape itself (`result` key) is
    confirmed - it is the only thing consistently shown across every
    official example given for this phase.
    """

    model_config = ConfigDict(extra="ignore")

    result: Any
