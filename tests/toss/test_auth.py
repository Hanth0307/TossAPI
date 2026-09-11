from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.core.exceptions import (
    DataValidationError,
    TossAuthenticationError,
    TossIpRestrictedError,
)
from app.toss.auth import TossOAuthClient
from tests.toss.conftest import FakeClock, make_base_client

CLIENT_ID = SecretStr("test-client-id")
CLIENT_SECRET = SecretStr("super-secret-value-should-never-leak")


def _token_response(*, expires_in: int = 3600) -> httpx.Response:
    return httpx.Response(
        200, json={"access_token": "tok-abc123", "token_type": "Bearer", "expires_in": expires_in}
    )


def test_fetches_and_returns_access_token(sleep_fn) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        assert request.url.path == "/oauth2/token"
        body = request.content.decode()
        assert "grant_type=client_credentials" in body
        return _token_response()

    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    token = client.get_valid_token()

    assert token == "tok-abc123"
    assert calls["count"] == 1


def test_caches_token_until_expiring(sleep_fn) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return _token_response(expires_in=3600)

    clock = FakeClock()
    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        clock=clock.now,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    client.get_valid_token()
    client.get_valid_token()

    assert calls["count"] == 1


def test_refreshes_after_expiry_leeway(sleep_fn) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return _token_response(expires_in=60)

    clock = FakeClock()
    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        clock=clock.now,
        expiry_leeway_seconds=10,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    client.get_valid_token()
    clock.advance(55)  # within 10s of the 60s expiry
    client.get_valid_token()

    assert calls["count"] == 2


def test_invalidate_forces_refetch(sleep_fn) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return _token_response()

    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    client.get_valid_token()
    client.invalidate()
    client.get_valid_token()

    assert calls["count"] == 2


def test_missing_access_token_raises_data_validation_error(sleep_fn) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "Bearer", "expires_in": 3600})

    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    with pytest.raises(DataValidationError):
        client.get_valid_token()


def test_401_from_token_endpoint_raises_authentication_error(sleep_fn) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "invalid_client"})

    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    with pytest.raises(TossAuthenticationError):
        client.get_valid_token()


def test_403_from_token_endpoint_raises_ip_restricted_error(sleep_fn) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={})

    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    with pytest.raises(TossIpRestrictedError):
        client.get_valid_token()


def test_client_secret_never_appears_in_a_raised_exception_message(sleep_fn) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "invalid_client"})

    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    with pytest.raises(TossAuthenticationError) as excinfo:
        client.get_valid_token()

    assert CLIENT_SECRET.get_secret_value() not in str(excinfo.value)
    assert CLIENT_SECRET.get_secret_value() not in repr(excinfo.value)


def test_client_secret_never_appears_in_client_repr() -> None:
    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )
    assert CLIENT_SECRET.get_secret_value() not in repr(client)
    assert CLIENT_SECRET.get_secret_value() not in str(vars(client))
