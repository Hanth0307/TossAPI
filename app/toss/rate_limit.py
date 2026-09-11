"""Client-side pacing to stay under Toss's per-group TPS limits.

The official docs confirm four rate-limit groups and their TPS caps
(AUTH 5, ACCOUNT 1, ASSET 5, STOCK 5) but note operational limits can
change - so these are configurable defaults, not constants baked into
request logic, and a 429 response is still mapped to a precise
`TossRateLimitError` regardless of whether this throttle fires first
(see `app.toss.error_mapping`).

The docs do not specify which of the 13 Phase 02 endpoints belongs to
which group beyond what their own category names imply. Endpoints
literally named "Account"/"Asset" map to the identically-named group;
Market Data/Stock Info map to STOCK. The Order Read-Only and Order
Info Read-Only categories have no confirmed group, so they default to
the most conservative one (ACCOUNT, 1 TPS) until confirmed - see
`app.toss.client.DEFAULT_ENDPOINT_GROUPS` and ADR 0007.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from enum import StrEnum


class RateLimitGroup(StrEnum):
    AUTH = "AUTH"
    ACCOUNT = "ACCOUNT"
    ASSET = "ASSET"
    STOCK = "STOCK"


# Confirmed by the official docs (subject to change - see module docstring).
DEFAULT_GROUP_TPS: dict[RateLimitGroup, float] = {
    RateLimitGroup.AUTH: 5.0,
    RateLimitGroup.ACCOUNT: 1.0,
    RateLimitGroup.ASSET: 5.0,
    RateLimitGroup.STOCK: 5.0,
}


class GroupThrottle:
    """Waits, if necessary, so consecutive calls in the same group stay
    at or below `1 / tps` apart. Purely a client-side courtesy: it
    does not replace or suppress 429 handling.
    """

    def __init__(
        self,
        group_tps: Mapping[RateLimitGroup, float] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._tps: dict[RateLimitGroup, float] = dict(DEFAULT_GROUP_TPS)
        if group_tps:
            self._tps.update(group_tps)
        self._clock = clock
        self._sleep = sleep_fn
        self._last_call_at: dict[RateLimitGroup, float] = {}

    def wait(self, group: RateLimitGroup) -> None:
        tps = self._tps.get(group)
        if not tps or tps <= 0:
            return

        min_interval = 1.0 / tps
        last = self._last_call_at.get(group)
        if last is not None:
            elapsed = self._clock() - last
            remaining = min_interval - elapsed
            if remaining > 0:
                self._sleep(remaining)

        self._last_call_at[group] = self._clock()
