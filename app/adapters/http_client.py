"""Common timeout/retry policy for outbound HTTP calls to external APIs.

Two named policies are provided:

- `DEFAULT_RETRY_POLICY`: for read-only / idempotent calls (quotes,
  account balance, news, DART filings, ...). Retries on timeouts and a
  small set of transient HTTP status codes, with exponential backoff.

- `NO_RETRY_POLICY`: MUST be used for order-mutating calls (place,
  cancel, modify order). An automatic retry after a timeout cannot
  tell whether the original request already reached the broker, so
  retrying blindly risks a duplicate order. Order-placing code (not
  implemented in Phase 00) must use this policy and handle failures
  explicitly - e.g. by checking order status before resubmitting, or
  surfacing the failure to a human. See
  docs/architecture/0004-external-api-timeout-retry-policy.md.

No response schema or field names are assumed anywhere in this module -
that is the responsibility of each concrete adapter, once its API's
real responses have been verified.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.exceptions import (
    ExternalAPIError,
    ExternalAPIRetryExhaustedError,
    ExternalAPITimeoutError,
)


@dataclass(frozen=True)
class RetryPolicy:
    timeout_seconds: float = 10.0
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    retry_status_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({408, 429, 500, 502, 503, 504})
    )


DEFAULT_RETRY_POLICY = RetryPolicy()

# max_retries=0: never auto-retry. Required for order-mutating calls.
NO_RETRY_POLICY = RetryPolicy(max_retries=0)


class BaseApiClient:
    """Thin HTTP client wrapper that applies a `RetryPolicy`.

    Subclass this per external integration once its API contract is
    known. This base class only handles transport-level concerns
    (timeout, retry, backoff) - it does not parse or validate any
    response body.
    """

    def __init__(
        self,
        base_url: str,
        policy: RetryPolicy = DEFAULT_RETRY_POLICY,
        client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._policy = policy
        self._client = client or httpx.Client(timeout=policy.timeout_seconds)
        self._sleep_fn = sleep_fn

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self._base_url}/{path.lstrip('/')}"

        for attempt in range(self._policy.max_retries + 1):
            is_last_attempt = attempt == self._policy.max_retries
            try:
                response = self._client.request(
                    method, url, timeout=self._policy.timeout_seconds, **kwargs
                )
            except httpx.TimeoutException as exc:
                if is_last_attempt:
                    raise ExternalAPITimeoutError(f"Timed out calling {url}") from exc
            except httpx.HTTPError as exc:
                if is_last_attempt:
                    raise ExternalAPIError(f"Network error calling {url}: {exc}") from exc
            else:
                if response.status_code not in self._policy.retry_status_codes:
                    return response
                if is_last_attempt:
                    raise ExternalAPIRetryExhaustedError(
                        f"Exhausted retries calling {url} "
                        f"(last status={response.status_code})"
                    )

            self._sleep_fn(
                self._policy.backoff_base_seconds
                * (self._policy.backoff_multiplier**attempt)
            )

        # Unreachable: the loop above always returns or raises on the
        # last attempt.
        raise AssertionError("unreachable")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BaseApiClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
