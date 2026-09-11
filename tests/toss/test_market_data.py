"""Tests using the exact official JSON examples given for Phase 02."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from app.core.exceptions import DataValidationError
from app.toss.auth import TossOAuthClient
from app.toss.client import TossRestClient
from app.toss.market_data import MAX_CANDLE_COUNT, CandleInterval, MarketDataAdapter
from app.toss.models import OrderBookLevel
from app.toss.rate_limit import GroupThrottle
from tests.toss.conftest import make_base_client

PRICE_RESPONSE = {
    "result": [
        {
            "symbol": "005930",
            "timestamp": "2026-03-25T09:30:00.123+09:00",
            "lastPrice": "72000",
            "currency": "KRW",
        }
    ]
}

ORDERBOOK_RESPONSE = {
    "result": {
        "timestamp": "2026-03-25T09:30:00.123+09:00",
        "currency": "KRW",
        "asks": [{"price": "72300", "volume": "1200"}],
        "bids": [{"price": "72000", "volume": "5200"}],
    }
}

TRADES_RESPONSE = {
    "result": [
        {
            "price": "72000",
            "volume": "120",
            "timestamp": "2026-03-25T09:30:42.000+09:00",
            "currency": "KRW",
        }
    ]
}

CANDLES_RESPONSE = {
    "result": {
        "candles": [
            {
                "timestamp": "2026-03-25T09:00:00+09:00",
                "openPrice": "71600",
                "highPrice": "72300",
                "lowPrice": "71500",
                "closePrice": "72000",
                "volume": "3521000",
                "currency": "KRW",
            }
        ],
        "nextBefore": "2026-03-24T09:00:00+09:00",
    }
}


def _adapter(handler, *, capture_raw_payload: bool = False) -> MarketDataAdapter:
    def token_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 3600})

    oauth = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=SecretStr("id"),
        client_secret=SecretStr("secret"),
        sleep_fn=lambda _s: None,
        http_client=make_base_client(token_handler, sleep_fn=lambda _s: None),
    )
    client = TossRestClient(
        base_url="https://openapi.tossinvest.com",
        oauth_client=oauth,
        read_only_mode=True,
        sleep_fn=lambda _s: None,
        throttle=GroupThrottle(sleep_fn=lambda _s: None),
        http_client=make_base_client(handler, sleep_fn=lambda _s: None),
    )
    return MarketDataAdapter(client, capture_raw_payload=capture_raw_payload)


def test_get_price_maps_official_example_to_normalized_quote() -> None:
    adapter = _adapter(lambda request: httpx.Response(200, json=PRICE_RESPONSE))

    quote = adapter.get_price("005930")

    assert quote.symbol == "005930"
    assert quote.last_price == Decimal("72000")
    assert quote.currency == "KRW"
    assert isinstance(quote.last_price, Decimal)
    assert quote.metadata.source == "toss_openapi"
    assert quote.metadata.event_time is not None
    assert quote.metadata.event_time.tzinfo is not None
    assert quote.metadata.raw_payload is None  # capture_raw_payload defaults to False


def test_get_price_can_optionally_capture_raw_payload() -> None:
    adapter = _adapter(
        lambda request: httpx.Response(200, json=PRICE_RESPONSE), capture_raw_payload=True
    )

    quote = adapter.get_price("005930")

    assert quote.metadata.raw_payload == PRICE_RESPONSE


def test_get_price_empty_result_raises_data_validation_error() -> None:
    adapter = _adapter(lambda request: httpx.Response(200, json={"result": []}))

    with pytest.raises(DataValidationError):
        adapter.get_price("005930")


def test_get_orderbook_maps_official_example() -> None:
    adapter = _adapter(lambda request: httpx.Response(200, json=ORDERBOOK_RESPONSE))

    snapshot = adapter.get_orderbook("005930")

    assert snapshot.symbol == "005930"
    assert snapshot.currency == "KRW"
    assert snapshot.asks == [OrderBookLevel(price=Decimal("72300"), volume=Decimal("1200"))]
    assert snapshot.bids[0].price == Decimal("72000")
    assert snapshot.bids[0].volume == Decimal("5200")


def test_get_trades_maps_official_example() -> None:
    adapter = _adapter(lambda request: httpx.Response(200, json=TRADES_RESPONSE))

    trades = adapter.get_trades("005930")

    assert len(trades) == 1
    assert trades[0].symbol == "005930"
    assert trades[0].price == Decimal("72000")
    assert trades[0].volume == Decimal("120")
    assert trades[0].currency == "KRW"
    assert trades[0].metadata.event_time is not None


def test_get_candles_maps_official_example_and_next_before() -> None:
    adapter = _adapter(lambda request: httpx.Response(200, json=CANDLES_RESPONSE))

    series = adapter.get_candles("005930", CandleInterval.ONE_DAY, 1)

    assert series.symbol == "005930"
    assert series.interval == "1d"
    assert series.next_before == "2026-03-24T09:00:00+09:00"
    assert len(series.candles) == 1
    candle = series.candles[0]
    assert candle.open_price == Decimal("71600")
    assert candle.high_price == Decimal("72300")
    assert candle.low_price == Decimal("71500")
    assert candle.close_price == Decimal("72000")
    assert candle.volume == Decimal("3521000")
    assert candle.timestamp.tzinfo is not None


@pytest.mark.parametrize("count", [0, 201, -1])
def test_get_candles_rejects_out_of_range_count(count: int) -> None:
    adapter = _adapter(lambda request: httpx.Response(200, json=CANDLES_RESPONSE))

    with pytest.raises(ValueError):
        adapter.get_candles("005930", CandleInterval.ONE_MINUTE, count)


def test_get_candles_accepts_boundary_counts() -> None:
    adapter = _adapter(lambda request: httpx.Response(200, json=CANDLES_RESPONSE))

    adapter.get_candles("005930", CandleInterval.ONE_MINUTE, 1)
    adapter.get_candles("005930", CandleInterval.ONE_MINUTE, MAX_CANDLE_COUNT)


def test_get_price_limits_returns_unparsed_record_preserving_raw_result() -> None:
    raw_result = {"upperLimit": "79200", "lowerLimit": "64800"}  # illustrative shape, not confirmed
    adapter = _adapter(lambda request: httpx.Response(200, json={"result": raw_result}))

    record = adapter.get_price_limits("005930")

    assert record.result == raw_result
    assert record.metadata.event_time is None
    assert record.metadata.source == "toss_openapi"


def test_get_stocks_returns_unparsed_record() -> None:
    # illustrative shape, not a confirmed schema
    raw_result = [{"symbol": "005930", "name": "Samsung Electronics"}]
    adapter = _adapter(lambda request: httpx.Response(200, json={"result": raw_result}))

    record = adapter.get_stocks()

    assert record.result == raw_result
