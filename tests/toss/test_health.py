from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.core.exceptions import TossAuthenticationError
from app.toss.auth import TossOAuthClient
from app.toss.health import check_auth_health
from tests.toss.conftest import make_base_client


def test_check_auth_health_reports_ok_and_expiry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 3600})

    oauth = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=SecretStr("id"),
        client_secret=SecretStr("secret"),
        sleep_fn=lambda _s: None,
        http_client=make_base_client(handler, sleep_fn=lambda _s: None),
    )

    result = check_auth_health(oauth)

    assert result.ok is True
    assert result.token_expires_at is not None
    assert result.checked_at is not None


def test_check_auth_health_forces_a_fresh_fetch_even_if_cached() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 3600})

    oauth = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=SecretStr("id"),
        client_secret=SecretStr("secret"),
        sleep_fn=lambda _s: None,
        http_client=make_base_client(handler, sleep_fn=lambda _s: None),
    )
    oauth.get_valid_token()  # pre-populate the cache
    assert calls["count"] == 1

    check_auth_health(oauth)

    assert calls["count"] == 2


def test_check_auth_health_raises_on_failure_rather_than_reporting_not_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={})

    oauth = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=SecretStr("id"),
        client_secret=SecretStr("secret"),
        sleep_fn=lambda _s: None,
        http_client=make_base_client(handler, sleep_fn=lambda _s: None),
    )

    with pytest.raises(TossAuthenticationError):
        check_auth_health(oauth)
