from __future__ import annotations

import httpx
import pytest

from app.adapters.http_client import (
    DEFAULT_RETRY_POLICY,
    NO_RETRY_POLICY,
    BaseApiClient,
    RetryPolicy,
)
from app.core.exceptions import (
    ExternalAPIRetryExhaustedError,
    ExternalAPITimeoutError,
)


def _client_with_transport(transport: httpx.MockTransport, policy: RetryPolicy) -> BaseApiClient:
    httpx_client = httpx.Client(transport=transport)
    sleeps: list[float] = []
    client = BaseApiClient(
        base_url="https://example.test",
        policy=policy,
        client=httpx_client,
        sleep_fn=sleeps.append,
    )
    client.sleeps = sleeps  # type: ignore[attr-defined]
    return client


def test_successful_request_returns_response_without_retry() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"ok": True})

    client = _client_with_transport(httpx.MockTransport(handler), DEFAULT_RETRY_POLICY)
    response = client.request("GET", "/ping")

    assert response.status_code == 200
    assert calls["count"] == 1


def test_retries_on_retryable_status_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    client = _client_with_transport(
        httpx.MockTransport(handler), RetryPolicy(max_retries=3, backoff_base_seconds=0.01)
    )
    response = client.request("GET", "/flaky")

    assert response.status_code == 200
    assert calls["count"] == 3


def test_raises_after_exhausting_retries_on_persistent_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = _client_with_transport(
        httpx.MockTransport(handler), RetryPolicy(max_retries=2, backoff_base_seconds=0.01)
    )

    with pytest.raises(ExternalAPIRetryExhaustedError):
        client.request("GET", "/always-fails")


def test_raises_on_timeout_after_exhausting_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("boom", request=request)

    client = _client_with_transport(
        httpx.MockTransport(handler), RetryPolicy(max_retries=2, backoff_base_seconds=0.01)
    )

    with pytest.raises(ExternalAPITimeoutError):
        client.request("GET", "/times-out")


def test_no_retry_policy_never_retries_a_failure() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(500)

    client = _client_with_transport(httpx.MockTransport(handler), NO_RETRY_POLICY)

    with pytest.raises(ExternalAPIRetryExhaustedError):
        client.request("POST", "/orders")

    assert calls["count"] == 1
