"""Proves client_id/client_secret/access_token/account_seq never leak
into logs, exceptions, or object reprs - the explicit requirement for
this phase (item 6).
"""

from __future__ import annotations

import logging

import httpx
from pydantic import SecretStr

from app.core.exceptions import TossAuthenticationError
from app.toss.auth import TossOAuthClient
from app.toss.client import TossRestClient
from app.toss.rate_limit import GroupThrottle
from tests.toss.conftest import make_base_client

CLIENT_ID = SecretStr("redact-client-id")
CLIENT_SECRET = SecretStr("redact-client-secret-value")
ACCOUNT_SEQ = SecretStr("redact-account-seq-999")
ACCESS_TOKEN = "redact-access-token-abcxyz"

SECRETS = (
    CLIENT_ID.get_secret_value(),
    CLIENT_SECRET.get_secret_value(),
    ACCOUNT_SEQ.get_secret_value(),
    ACCESS_TOKEN,
)


def _build_client(*, final_status: int) -> TossRestClient:
    def token_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600})

    def data_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(final_status, json={"code": "some-error"})

    oauth = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        sleep_fn=lambda _s: None,
        http_client=make_base_client(token_handler, sleep_fn=lambda _s: None),
    )
    return TossRestClient(
        base_url="https://openapi.tossinvest.com",
        oauth_client=oauth,
        account_seq=ACCOUNT_SEQ,
        read_only_mode=True,
        sleep_fn=lambda _s: None,
        throttle=GroupThrottle(sleep_fn=lambda _s: None),
        http_client=make_base_client(data_handler, sleep_fn=lambda _s: None),
    )


def test_no_secret_leaks_through_a_full_auth_failure_flow(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    client = _build_client(final_status=401)

    try:
        client.get("/api/v1/holdings", requires_account=True)
    except TossAuthenticationError as exc:
        error_text = f"{exc}{exc!r}"
    else:
        raise AssertionError("expected TossAuthenticationError")

    log_text = caplog.text
    for secret in SECRETS:
        assert secret not in error_text
        assert secret not in log_text


def test_no_secret_leaks_when_rate_limited(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    client = _build_client(final_status=429)

    try:
        client.get("/api/v1/sellable-quantity", requires_account=True, params={"symbol": "005930"})
    except Exception as exc:  # noqa: BLE001 - want to inspect whatever was raised
        error_text = f"{exc}{exc!r}"
    else:
        raise AssertionError("expected an exception")

    log_text = caplog.text
    for secret in SECRETS:
        assert secret not in error_text
        assert secret not in log_text


def test_client_object_repr_never_contains_secrets() -> None:
    client = _build_client(final_status=200)
    dump = str(vars(client)) + repr(client)
    for secret in SECRETS[:3]:  # access token isn't held directly on TossRestClient
        assert secret not in dump
