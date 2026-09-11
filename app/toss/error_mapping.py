"""Maps a Toss HTTP response to a precisely-typed domain exception.

Dispatch is primarily by HTTP status code, which the official docs
confirm unambiguously: 401 auth failure, 403 unregistered-IP
rejection, 429 per-group rate limit, 5xx server-side failure. The
docs also confirm four literal error-code strings
(`edge-rate-limit-exceeded`, `rate-limit-exceeded`, `internal-error`,
`maintenance`) without showing the exact JSON envelope that carries
them, so `error_code` extraction below tries a couple of common
shapes defensively rather than assuming one fixed schema - status
code is always the authoritative signal, `error_code` is best-effort
detail attached when available.
"""

from __future__ import annotations

import httpx

from app.core.exceptions import (
    TossApiError,
    TossAuthenticationError,
    TossIpRestrictedError,
    TossRateLimitError,
    TossServerError,
)

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def extract_error_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None

    code = body.get("code")
    if isinstance(code, str):
        return code

    error = body.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        nested_code = error.get("code")
        if isinstance(nested_code, str):
            return nested_code

    return None


def extract_retry_after_seconds(response: httpx.Response) -> float | None:
    """Honors the standard `Retry-After` header (RFC 7231/6585) when present.

    This is a generic HTTP convention, not a Toss-specific field - the
    docs do not confirm Toss sends it, so callers must not assume a
    value is always available.
    """
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def raise_for_status(response: httpx.Response, *, context: str) -> None:
    """Raises the matching `TossApiError` subclass for a non-2xx response.

    A no-op for 2xx. Never returns a "best guess" result for a failed
    call - see docs/architecture/0007-toss-api-integration.md.
    """
    if 200 <= response.status_code < 300:
        return

    error_code = extract_error_code(response)

    if response.status_code == 401:
        raise TossAuthenticationError(
            f"{context}: authentication failed (401)",
            status_code=401,
            error_code=error_code,
        )
    if response.status_code == 403:
        raise TossIpRestrictedError(
            f"{context}: request forbidden (403) - possibly an unregistered "
            "caller IP; see the Open API allow-list setting",
            status_code=403,
            error_code=error_code,
        )
    if response.status_code == 429:
        raise TossRateLimitError(
            f"{context}: rate limit exceeded (429)",
            status_code=429,
            error_code=error_code,
            retry_after=extract_retry_after_seconds(response),
        )
    if 500 <= response.status_code < 600:
        raise TossServerError(
            f"{context}: server error ({response.status_code})",
            status_code=response.status_code,
            error_code=error_code,
        )

    raise TossApiError(
        f"{context}: unexpected status {response.status_code}",
        status_code=response.status_code,
        error_code=error_code,
    )
