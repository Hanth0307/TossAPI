"""Opt-in integration test against the real Toss Open API.

Skipped by default - and in this environment, always skipped, since:

1. This session cannot reach `openapi.tossinvest.com` at all (the
   organization's network egress policy blocks `*.tossinvest.com`,
   confirmed during Phase 02 planning - see
   docs/architecture/0007-toss-api-integration.md).
2. No real Toss credentials were ever provided to this session.

Set `TOSS_INTEGRATION_TEST=1` *and* real `TOSS_CLIENT_ID`/
`TOSS_CLIENT_SECRET` (and, for the account check,
`TOSS_ACCOUNT_SEQ`) to run this outside this environment. The mock/
contract tests in `test_auth.py`, `test_client.py`,
`test_market_data.py`, and `test_portfolio.py` are what stand in for
this here - per the "권한이 없으면 mock contract test로 대체하고 이유를
기록" completion condition.
"""

from __future__ import annotations

import os

import pytest

from app.core.config import Settings
from app.toss.factory import build_toss_gateways
from app.toss.health import check_auth_health

pytestmark = pytest.mark.skipif(
    os.environ.get("TOSS_INTEGRATION_TEST") != "1",
    reason=(
        "opt-in only - set TOSS_INTEGRATION_TEST=1 plus real "
        "TOSS_CLIENT_ID/TOSS_CLIENT_SECRET to run against the real API"
    ),
)


def test_auth_health_check_against_the_real_api() -> None:
    settings = Settings()
    gateways = build_toss_gateways(settings)
    result = check_auth_health(gateways.market_data._client._oauth)  # type: ignore[attr-defined]
    assert result.ok


def test_get_price_against_the_real_api() -> None:
    settings = Settings()
    gateways = build_toss_gateways(settings)
    quote = gateways.market_data.get_price("005930")
    assert quote.symbol == "005930"


def test_get_holdings_against_the_real_api_if_account_configured() -> None:
    settings = Settings()
    if settings.toss_account_seq is None:
        pytest.skip("TOSS_ACCOUNT_SEQ not configured - no account access to test")
    gateways = build_toss_gateways(settings)
    record = gateways.portfolio.get_holdings()
    assert record.result is not None
