"""Fail-closed behavior and secret non-leakage for the provisional
OAuth token response parser (app/toss/token_parser.py).
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.exceptions import DataValidationError, TossAuthenticationError
from app.toss.auth import TossOAuthClient
from app.toss.token_parser import (
    TOKEN_RESPONSE_SCHEMA_VERIFIED,
    ParsedToken,
    ProvisionalTokenResponseParser,
)
from tests.toss.conftest import make_base_client

CLIENT_ID = SecretStr("parser-test-client-id")
CLIENT_SECRET = SecretStr("parser-test-client-secret-value")


def test_schema_is_recorded_as_not_yet_verified() -> None:
    # This is a trip-wire, not a functional check: the flag must only
    # ever flip to True alongside real evidence (see the module
    # docstring and ADR 0007). If this test starts failing because
    # someone flipped it, that change needs real evidence attached,
    # not just this test updated.
    assert TOKEN_RESPONSE_SCHEMA_VERIFIED is False


def test_parser_accepts_the_provisional_shape() -> None:
    parser = ProvisionalTokenResponseParser()
    parsed = parser.parse(json.dumps({"access_token": "tok-1", "expires_in": 3600}).encode())
    assert parsed == ParsedToken(access_token="tok-1", expires_in=3600)


def test_parser_ignores_unknown_extra_fields() -> None:
    parser = ProvisionalTokenResponseParser()
    parsed = parser.parse(
        json.dumps(
            {"access_token": "tok-1", "expires_in": 3600, "token_type": "Bearer", "scope": "read"}
        ).encode()
    )
    assert parsed.access_token == "tok-1"


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b'{"access_token": "tok-1"}',  # missing expires_in
        b'{"expires_in": 3600}',  # missing access_token
        b'{"token": "tok-1", "ttl": 3600}',  # entirely different field names
        b"not json at all",
        b'["unexpected", "list"]',
    ],
)
def test_parser_fails_closed_on_any_unexpected_shape(body: bytes) -> None:
    parser = ProvisionalTokenResponseParser()
    with pytest.raises(DataValidationError):
        parser.parse(body)


def test_unexpected_token_response_shape_fails_closed_through_oauth_client(sleep_fn) -> None:
    """A 200 response that doesn't match the provisional shape must
    never produce a token - it must raise, not silently succeed with a
    partial/default token.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"totally": "unexpected", "shape": True})

    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    with pytest.raises(DataValidationError):
        client.get_valid_token()


def test_token_parsing_failure_never_leaks_response_body_or_secrets(sleep_fn) -> None:
    """Even if a malformed response happens to carry a secret/token-
    looking value in an unexpected field, it must never appear in the
    raised exception's message.
    """
    leaked_looking_value = "should-never-appear-in-any-exception-xyz789"

    def handler(request: httpx.Request) -> httpx.Response:
        # Deliberately the wrong field name ("token" instead of
        # "access_token") so parsing fails - but the value itself must
        # still never leak through the failure.
        return httpx.Response(200, json={"token": leaked_looking_value, "ttl": 60})

    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
    )

    with pytest.raises(DataValidationError) as excinfo:
        client.get_valid_token()

    assert leaked_looking_value not in str(excinfo.value)
    assert leaked_looking_value not in repr(excinfo.value)
    assert CLIENT_SECRET.get_secret_value() not in str(excinfo.value)


def test_custom_token_parser_can_be_injected_without_touching_oauth_client(sleep_fn) -> None:
    """Proves the isolation boundary: swapping the parser is enough to
    support a corrected real schema - TossOAuthClient itself needs no
    change.
    """

    class _FutureRealParser:
        def parse(self, raw_body: bytes) -> ParsedToken:
            data = json.loads(raw_body)
            return ParsedToken(access_token=data["realAccessToken"], expires_in=data["ttlSeconds"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"realAccessToken": "future-tok", "ttlSeconds": 120})

    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
        token_parser=_FutureRealParser(),
    )

    assert client.get_valid_token() == "future-tok"


def test_401_still_raised_correctly_when_a_custom_parser_is_injected(sleep_fn) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={})

    client = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        sleep_fn=sleep_fn,
        http_client=make_base_client(handler, sleep_fn=sleep_fn),
        token_parser=ProvisionalTokenResponseParser(),
    )

    with pytest.raises(TossAuthenticationError):
        client.get_valid_token()
