"""Wires `Settings` into a `MarketDataAdapter` / `PortfolioReadAdapter` pair.

The only place credentials are read from configuration - never
hardcoded, never logged (see `app.core.config.Settings` and
`tests/toss/test_secret_redaction.py`). Fails fast with a
`ConfigError` if credentials are missing or if
`toss_read_only_mode` has been turned off.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.exceptions import ConfigError
from app.toss.auth import TossOAuthClient
from app.toss.client import TossRestClient
from app.toss.market_data import MarketDataAdapter
from app.toss.portfolio import PortfolioReadAdapter


@dataclass(frozen=True)
class TossGateways:
    market_data: MarketDataAdapter
    portfolio: PortfolioReadAdapter


def build_toss_gateways(settings: Settings, *, capture_raw_payload: bool = False) -> TossGateways:
    if not settings.toss_read_only_mode:
        raise ConfigError(
            "toss_read_only_mode is False - refusing to build Toss gateways. "
            "Phase 02 ships no order-placing code; this flag exists so "
            "enabling write access is a deliberate, reviewed change."
        )
    if settings.toss_client_id is None or settings.toss_client_secret is None:
        raise ConfigError(
            "toss_client_id/toss_client_secret are not configured - set them "
            "in a local .env (see .env.example), never hardcode them."
        )

    oauth_client = TossOAuthClient(
        base_url=settings.toss_api_base_url,
        client_id=settings.toss_client_id,
        client_secret=settings.toss_client_secret,
        timeout_seconds=settings.http_timeout_seconds,
        max_retries=settings.http_max_retries,
    )
    rest_client = TossRestClient(
        base_url=settings.toss_api_base_url,
        oauth_client=oauth_client,
        account_seq=settings.toss_account_seq,
        read_only_mode=settings.toss_read_only_mode,
        timeout_seconds=settings.http_timeout_seconds,
        max_retries=settings.http_max_retries,
    )
    return TossGateways(
        market_data=MarketDataAdapter(rest_client, capture_raw_payload=capture_raw_payload),
        portfolio=PortfolioReadAdapter(rest_client, capture_raw_payload=capture_raw_payload),
    )
