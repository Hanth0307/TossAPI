"""Authentication health check for the Toss Open API.

A minimal, explicit way to answer "can we authenticate right now?"
without touching any account/market-data endpoint - useful as the
completion-gate health check and as a startup smoke test. A failure
here always raises (via `TossOAuthClient`/`error_mapping`); it never
reports "ok" based on stale/cached state - the cached token is
invalidated first, so this always performs a real token fetch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.toss.auth import TossOAuthClient


@dataclass(frozen=True)
class AuthHealthCheckResult:
    ok: bool
    checked_at: datetime
    token_expires_at: datetime | None


def check_auth_health(oauth_client: TossOAuthClient) -> AuthHealthCheckResult:
    """Forces a fresh token fetch and reports the result.

    Raises the matching `TossApiError` subclass on failure - a caller
    that wants a pass/fail boolean without an exception should catch
    `app.core.exceptions.TossApiError` around this call explicitly;
    this function does not swallow errors itself.
    """
    oauth_client.invalidate()
    token = oauth_client.get_valid_token()
    return AuthHealthCheckResult(
        ok=bool(token),
        checked_at=datetime.now(UTC),
        token_expires_at=oauth_client.cached_token_expires_at,
    )
