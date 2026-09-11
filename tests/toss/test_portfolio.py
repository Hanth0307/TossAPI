from __future__ import annotations

import httpx
from pydantic import SecretStr

from app.toss.auth import TossOAuthClient
from app.toss.client import TossRestClient
from app.toss.portfolio import PortfolioReadAdapter
from app.toss.rate_limit import GroupThrottle
from tests.toss.conftest import make_base_client

ACCOUNT_SEQ = SecretStr("acct-001")


def _adapter(handler) -> PortfolioReadAdapter:
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
        account_seq=ACCOUNT_SEQ,
        read_only_mode=True,
        sleep_fn=lambda _s: None,
        throttle=GroupThrottle(sleep_fn=lambda _s: None),
        http_client=make_base_client(handler, sleep_fn=lambda _s: None),
    )
    return PortfolioReadAdapter(client)


def _capture_account_header(seen: dict[str, str]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen["account_header"] = request.headers.get("X-Tossinvest-Account", "")
        seen["path"] = request.url.path
        return httpx.Response(200, json={"result": {"illustrative": "not a confirmed schema"}})

    return handler


def test_get_accounts_attaches_account_header_and_returns_unparsed_record() -> None:
    seen: dict[str, str] = {}
    adapter = _adapter(_capture_account_header(seen))

    record = adapter.get_accounts()

    assert seen["account_header"] == "acct-001"
    assert seen["path"] == "/api/v1/accounts"
    assert record.result == {"illustrative": "not a confirmed schema"}
    assert record.metadata.source == "toss_openapi"


def test_get_holdings_calls_confirmed_path() -> None:
    seen: dict[str, str] = {}
    adapter = _adapter(_capture_account_header(seen))

    adapter.get_holdings()

    assert seen["path"] == "/api/v1/holdings"
    assert seen["account_header"] == "acct-001"


def test_get_orders_calls_confirmed_path() -> None:
    seen: dict[str, str] = {}
    adapter = _adapter(_capture_account_header(seen))

    adapter.get_orders()

    assert seen["path"] == "/api/v1/orders"


def test_get_order_calls_path_with_order_id() -> None:
    seen: dict[str, str] = {}
    adapter = _adapter(_capture_account_header(seen))

    adapter.get_order("order-123")

    assert seen["path"] == "/api/v1/orders/order-123"


def test_get_buying_power_calls_confirmed_path() -> None:
    seen: dict[str, str] = {}
    adapter = _adapter(_capture_account_header(seen))

    adapter.get_buying_power()

    assert seen["path"] == "/api/v1/buying-power"


def test_get_sellable_quantity_calls_confirmed_path_with_symbol() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.params)
        return httpx.Response(200, json={"result": {}})

    adapter = _adapter(handler)
    adapter.get_sellable_quantity("005930")

    assert seen["path"] == "/api/v1/sellable-quantity"
    assert "005930" in seen["query"]


def test_get_commissions_calls_confirmed_path() -> None:
    seen: dict[str, str] = {}
    adapter = _adapter(_capture_account_header(seen))

    adapter.get_commissions()

    assert seen["path"] == "/api/v1/commissions"


def test_portfolio_adapter_has_no_order_mutating_method() -> None:
    public_methods = {name for name in dir(PortfolioReadAdapter) if not name.startswith("_")}
    forbidden = {"place_order", "create_order", "cancel_order", "modify_order", "post"}
    assert public_methods.isdisjoint(forbidden)
