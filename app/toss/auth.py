"""OAuth 2.0 Client Credentials token client for the Toss Open API.

Confirmed by the official docs: `POST /oauth2/token`,
`Content-Type: application/x-www-form-urlencoded`, body
`grant_type=client_credentials&client_id=...&client_secret=...`. The
token response JSON schema itself was not shown - see
`app.toss.dto.TokenResponseDto` for why RFC 6749's standard fields are
used instead of a guessed Toss-specific shape.

`client_id`/`client_secret` are never logged, and neither is the
issued access token - see `tests/toss/test_secret_redaction.py`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import SecretStr, ValidationError

from app.adapters.http_client import BaseApiClient, RetryPolicy
from app.core.exceptions import DataValidationError
from app.toss._retry import send_with_status_retry
from app.toss.dto import TokenResponseDto
from app.toss.error_mapping import raise_for_status
from app.toss.rate_limit import GroupThrottle, RateLimitGroup

TOKEN_PATH = "/oauth2/token"


@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_at: datetime


class TossOAuthClient:
    def __init__(
        self,
        base_url: str,
        client_id: SecretStr,
        client_secret: SecretStr,
        *,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        backoff_base_seconds: float = 0.5,
        backoff_multiplier: float = 2.0,
        expiry_leeway_seconds: float = 30.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep_fn: Callable[[float], None] = time.sleep,
        throttle: GroupThrottle | None = None,
        http_client: BaseApiClient | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._max_retries = max_retries
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_multiplier = backoff_multiplier
        self._expiry_leeway_seconds = expiry_leeway_seconds
        self._clock = clock
        self._sleep_fn = sleep_fn
        self._throttle = throttle or GroupThrottle()
        self._http = http_client or BaseApiClient(
            base_url=base_url,
            policy=RetryPolicy(
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                retry_status_codes=frozenset(),
            ),
            sleep_fn=sleep_fn,
        )
        self._cached_token: AccessToken | None = None

    def get_valid_token(self) -> str:
        if self._cached_token is None or self._is_expiring(self._cached_token):
            self._cached_token = self._fetch_token()
        return self._cached_token.value

    def invalidate(self) -> None:
        self._cached_token = None

    @property
    def cached_token_expires_at(self) -> datetime | None:
        return self._cached_token.expires_at if self._cached_token is not None else None

    def _is_expiring(self, token: AccessToken) -> bool:
        return self._clock() >= token.expires_at - timedelta(seconds=self._expiry_leeway_seconds)

    def _fetch_token(self) -> AccessToken:
        self._throttle.wait(RateLimitGroup.AUTH)

        response = send_with_status_retry(
            self._http,
            "POST",
            TOKEN_PATH,
            max_retries=self._max_retries,
            backoff_base_seconds=self._backoff_base_seconds,
            backoff_multiplier=self._backoff_multiplier,
            sleep_fn=self._sleep_fn,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id.get_secret_value(),
                "client_secret": self._client_secret.get_secret_value(),
            },
        )
        raise_for_status(response, context="POST /oauth2/token")

        try:
            token_dto = TokenResponseDto.model_validate_json(response.content)
        except ValidationError as exc:
            # Deliberately not including exc's repr in the message: pydantic
            # error reprs do not echo input values for missing fields, but
            # keep this defensive rather than assuming that in all pydantic
            # versions.
            raise DataValidationError(
                "Toss token response did not match the expected OAuth2 shape "
                "(access_token/expires_in) - see app/toss/dto.py::TokenResponseDto"
            ) from exc

        expires_at = self._clock() + timedelta(seconds=token_dto.expires_in)
        return AccessToken(value=token_dto.access_token, expires_at=expires_at)
