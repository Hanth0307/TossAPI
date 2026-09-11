"""Low-level authenticated REST client for the Toss Open API.

Exposes exactly one HTTP verb: `get()`. There is no `post`/`put`/
`delete`/generic `request()` method - an order-mutating call is
therefore not just "not implemented", it is not expressible through
this client at all (see ADR 0007). Construction fails immediately
unless `Settings.toss_read_only_mode` is `True`.

Every call attaches `Authorization: Bearer {access_token}`; calls with
`requires_account=True` also attach `X-Tossinvest-Account`, per the
official docs' "계좌·자산·주문 API" requirement. A 401 triggers one
token refresh + retry (handles ordinary expiry); a 401 that persists
past that, a 403 (IP not allow-listed), a 429 (rate limit), or a 5xx
always raises a precisely-typed exception - never a stale/default
result (see `app.toss.error_mapping`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr

from app.adapters.http_client import BaseApiClient, RetryPolicy
from app.core.exceptions import ConfigError
from app.toss._retry import send_with_status_retry
from app.toss.auth import TossOAuthClient
from app.toss.error_mapping import raise_for_status
from app.toss.rate_limit import GroupThrottle, RateLimitGroup

# Best-effort default group assignment - see app/toss/rate_limit.py for why
# the Order Read-Only / Order Info Read-Only endpoints fall back to the most
# conservative (ACCOUNT) group rather than a confirmed one.
DEFAULT_ENDPOINT_GROUPS: dict[str, RateLimitGroup] = {
    "/api/v1/orderbook": RateLimitGroup.STOCK,
    "/api/v1/prices": RateLimitGroup.STOCK,
    "/api/v1/trades": RateLimitGroup.STOCK,
    "/api/v1/price-limits": RateLimitGroup.STOCK,
    "/api/v1/candles": RateLimitGroup.STOCK,
    "/api/v1/stocks": RateLimitGroup.STOCK,
    "/api/v1/accounts": RateLimitGroup.ACCOUNT,
    "/api/v1/holdings": RateLimitGroup.ASSET,
    "/api/v1/orders": RateLimitGroup.ACCOUNT,
    "/api/v1/buying-power": RateLimitGroup.ACCOUNT,
    "/api/v1/sellable-quantity": RateLimitGroup.ACCOUNT,
    "/api/v1/commissions": RateLimitGroup.ACCOUNT,
}


@dataclass(frozen=True)
class TossResponseEnvelope:
    payload: dict[str, Any]
    received_at: datetime


def _default_group_for(path: str) -> RateLimitGroup:
    # /api/v1/orders/{orderId} etc. - match by prefix.
    for known_path, group in DEFAULT_ENDPOINT_GROUPS.items():
        if path == known_path or path.startswith(known_path + "/"):
            return group
    return RateLimitGroup.ACCOUNT


class TossRestClient:
    def __init__(
        self,
        base_url: str,
        oauth_client: TossOAuthClient,
        *,
        account_seq: SecretStr | None = None,
        read_only_mode: bool,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        backoff_base_seconds: float = 0.5,
        backoff_multiplier: float = 2.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        throttle: GroupThrottle | None = None,
        http_client: BaseApiClient | None = None,
    ) -> None:
        if not read_only_mode:
            raise ConfigError(
                "TossRestClient refuses to start: toss_read_only_mode is False. "
                "Phase 02 ships no order-placing code at all - flip this flag "
                "only alongside a reviewed change that actually adds one."
            )

        self._oauth = oauth_client
        self._account_seq = account_seq
        self._max_retries = max_retries
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_multiplier = backoff_multiplier
        self._sleep_fn = sleep_fn
        self._clock = clock
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

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        requires_account: bool = False,
        group: RateLimitGroup | None = None,
    ) -> TossResponseEnvelope:
        if requires_account and self._account_seq is None:
            raise ConfigError(
                f"{path} requires an account (X-Tossinvest-Account) but no "
                "account_seq was configured on this TossRestClient"
            )

        resolved_group = group or _default_group_for(path)
        response = self._send(
            path, params=params, requires_account=requires_account, group=resolved_group
        )

        if response.status_code == 401:
            self._oauth.invalidate()
            response = self._send(
                path, params=params, requires_account=requires_account, group=resolved_group
            )

        raise_for_status(response, context=f"GET {path}")
        return TossResponseEnvelope(payload=response.json(), received_at=self._clock())

    def _send(
        self,
        path: str,
        *,
        params: dict[str, Any] | None,
        requires_account: bool,
        group: RateLimitGroup,
    ) -> httpx.Response:
        self._throttle.wait(group)
        headers = {"Authorization": f"Bearer {self._oauth.get_valid_token()}"}
        if requires_account:
            assert self._account_seq is not None  # checked by caller
            headers["X-Tossinvest-Account"] = self._account_seq.get_secret_value()

        return send_with_status_retry(
            self._http,
            "GET",
            path,
            max_retries=self._max_retries,
            backoff_base_seconds=self._backoff_base_seconds,
            backoff_multiplier=self._backoff_multiplier,
            sleep_fn=self._sleep_fn,
            params=params,
            headers=headers,
        )
