"""Status-code-aware retry loop shared by `auth.py` and `client.py`.

`app.adapters.http_client.BaseApiClient` is used underneath with an
empty `retry_status_codes` set, so it only retries on timeout (its own
well-tested behavior, unchanged) and always returns the raw response
for any status code - letting this module retry the specific
transient statuses Toss's own docs call out (429, 5xx) while keeping
the exact response available for `error_mapping.raise_for_status` to
turn into a precisely-typed exception once retries are exhausted.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app.adapters.http_client import BaseApiClient
from app.toss.error_mapping import RETRYABLE_STATUS_CODES, extract_retry_after_seconds


def send_with_status_retry(
    base_client: BaseApiClient,
    method: str,
    path: str,
    *,
    max_retries: int,
    backoff_base_seconds: float,
    backoff_multiplier: float,
    sleep_fn: Callable[[float], None],
    **kwargs: Any,
) -> httpx.Response:
    response: httpx.Response
    for attempt in range(max_retries + 1):
        response = base_client.request(method, path, **kwargs)

        if response.status_code not in RETRYABLE_STATUS_CODES or attempt == max_retries:
            return response

        retry_after = extract_retry_after_seconds(response) if response.status_code == 429 else None
        delay = retry_after if retry_after is not None else backoff_base_seconds * (
            backoff_multiplier**attempt
        )
        sleep_fn(delay)

    return response
