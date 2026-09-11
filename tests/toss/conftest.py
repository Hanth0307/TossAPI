"""Shared fixtures for `app.toss` tests.

Every test in this package uses `httpx.MockTransport` - no real
network call, no real credentials. `tests/toss/test_integration_live.py`
is the sole opt-in exception (skipped unless explicitly enabled).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.http_client import BaseApiClient, RetryPolicy


class FakeClock:
    """Deterministic, manually-advanced clock for expiry/backoff tests."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._now += timedelta(seconds=seconds)


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def recorded_sleeps() -> list[float]:
    return []


@pytest.fixture
def sleep_fn(recorded_sleeps: list[float]) -> Callable[[float], None]:
    def _sleep(seconds: float) -> None:
        recorded_sleeps.append(seconds)

    return _sleep


def make_base_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_retries: int = 0,
    sleep_fn: Callable[[float], None] = lambda _seconds: None,
) -> BaseApiClient:
    """A `BaseApiClient` wired to a `MockTransport`, matching how
    `app.toss` constructs its own clients (no status-based retry at
    this layer - see `app/toss/_retry.py`).
    """
    httpx_client = httpx.Client(transport=httpx.MockTransport(handler))
    return BaseApiClient(
        base_url="https://openapi.tossinvest.com",
        policy=RetryPolicy(max_retries=max_retries, retry_status_codes=frozenset()),
        client=httpx_client,
        sleep_fn=sleep_fn,
    )
