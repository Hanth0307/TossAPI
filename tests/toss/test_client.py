from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.core.exceptions import (
    ConfigError,
    TossAuthenticationError,
    TossIpRestrictedError,
    TossRateLimitError,
    TossServerError,
)
from app.toss.auth import TossOAuthClient
from app.toss.client import TossRestClient
from app.toss.rate_limit import GroupThrottle
from tests.toss.conftest import make_base_client

ACCOUNT_SEQ = SecretStr("acct-001")


def _oauth_stub(sleep_fn) -> TossOAuthClient:
    def token_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 3600})

    return TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=SecretStr("id"),
        client_secret=SecretStr("secret"),
        sleep_fn=sleep_fn,
        http_client=make_base_client(token_handler, sleep_fn=sleep_fn),
    )


def _no_throttle() -> GroupThrottle:
    return GroupThrottle(sleep_fn=lambda _s: None)


def test_successful_get_returns_envelope(sleep_fn) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok-1"
        return httpx.Response(200, json={"result": [{"symbol": "005930"}]})

    client = TossRestClient(
        base_url="https://openapi.tossinvest.com",
        oauth_client=_oauth_stub(sleep_fn),
        read_only_mode=True,
        sleep_fn=sleep_fn,
        throttle=_no_throttle(),
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    envelope = client.get("/api/v1/prices", params={"symbol": "005930"})

    assert envelope.payload == {"result": [{"symbol": "005930"}]}


def test_requires_account_attaches_header_when_configured(sleep_fn) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["account_header"] = request.headers.get("X-Tossinvest-Account", "")
        return httpx.Response(200, json={"result": {}})

    client = TossRestClient(
        base_url="https://openapi.tossinvest.com",
        oauth_client=_oauth_stub(sleep_fn),
        account_seq=ACCOUNT_SEQ,
        read_only_mode=True,
        sleep_fn=sleep_fn,
        throttle=_no_throttle(),
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    client.get("/api/v1/holdings", requires_account=True)

    assert captured["account_header"] == "acct-001"


def test_requires_account_without_configured_account_raises_config_error(sleep_fn) -> None:
    client = TossRestClient(
        base_url="https://openapi.tossinvest.com",
        oauth_client=_oauth_stub(sleep_fn),
        read_only_mode=True,
        sleep_fn=sleep_fn,
        throttle=_no_throttle(),
        http_client=make_base_client(lambda r: httpx.Response(200, json={}), sleep_fn=sleep_fn),
    )

    with pytest.raises(ConfigError):
        client.get("/api/v1/holdings", requires_account=True)


def test_401_triggers_one_refresh_then_succeeds(sleep_fn) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(401, json={})
        return httpx.Response(200, json={"result": []})

    client = TossRestClient(
        base_url="https://openapi.tossinvest.com",
        oauth_client=_oauth_stub(sleep_fn),
        read_only_mode=True,
        sleep_fn=sleep_fn,
        throttle=_no_throttle(),
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    envelope = client.get("/api/v1/prices", params={"symbol": "005930"})

    assert envelope.payload == {"result": []}
    assert calls["count"] == 2


def test_persistent_401_raises_authentication_error(sleep_fn) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={})

    client = TossRestClient(
        base_url="https://openapi.tossinvest.com",
        oauth_client=_oauth_stub(sleep_fn),
        read_only_mode=True,
        sleep_fn=sleep_fn,
        throttle=_no_throttle(),
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    with pytest.raises(TossAuthenticationError):
        client.get("/api/v1/prices", params={"symbol": "005930"})


def test_403_raises_ip_restricted_error(sleep_fn) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={})

    client = TossRestClient(
        base_url="https://openapi.tossinvest.com",
        oauth_client=_oauth_stub(sleep_fn),
        read_only_mode=True,
        sleep_fn=sleep_fn,
        throttle=_no_throttle(),
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    with pytest.raises(TossIpRestrictedError):
        client.get("/api/v1/prices", params={"symbol": "005930"})


def test_429_retries_then_raises_rate_limit_error_with_details(sleep_fn, recorded_sleeps) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, headers={"Retry-After": "2"}, json={"code": "rate-limit-exceeded"}
        )

    client = TossRestClient(
        base_url="https://openapi.tossinvest.com",
        oauth_client=_oauth_stub(sleep_fn),
        read_only_mode=True,
        max_retries=2,
        sleep_fn=sleep_fn,
        throttle=_no_throttle(),
        http_client=make_base_client(handler, max_retries=0, sleep_fn=sleep_fn),
    )

    with pytest.raises(TossRateLimitError) as excinfo:
        client.get("/api/v1/prices", params={"symbol": "005930"})

    assert excinfo.value.status_code == 429
    assert excinfo.value.error_code == "rate-limit-exceeded"
    assert excinfo.value.retry_after == 2.0
    assert recorded_sleeps == [2.0, 2.0]  # two retries before giving up on the third attempt


def test_5xx_raises_server_error(sleep_fn) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": "internal-error"})

    client = TossRestClient(
        base_url="https://openapi.tossinvest.com",
        oauth_client=_oauth_stub(sleep_fn),
        read_only_mode=True,
        max_retries=0,
        sleep_fn=sleep_fn,
        throttle=_no_throttle(),
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    with pytest.raises(TossServerError) as excinfo:
        client.get("/api/v1/prices", params={"symbol": "005930"})

    assert excinfo.value.status_code == 500
    assert excinfo.value.error_code == "internal-error"


def test_read_only_mode_false_refuses_to_construct(sleep_fn) -> None:
    with pytest.raises(ConfigError):
        TossRestClient(
            base_url="https://openapi.tossinvest.com",
            oauth_client=_oauth_stub(sleep_fn),
            read_only_mode=False,
        )


def test_client_has_no_write_capable_http_verb() -> None:
    public_methods = {name for name in dir(TossRestClient) if not name.startswith("_")}
    assert public_methods == {"get"}


def test_unknown_path_defaults_to_the_most_conservative_group() -> None:
    from app.toss.client import _default_group_for
    from app.toss.rate_limit import RateLimitGroup

    assert _default_group_for("/api/v1/some-future-endpoint") == RateLimitGroup.ACCOUNT
