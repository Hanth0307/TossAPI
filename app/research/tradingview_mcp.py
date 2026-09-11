"""Isolated TradingView MCP connectivity check.

This module answers exactly one question - "is the TradingView MCP
tool reachable right now?" - for a human doing strategy research. It
is never imported by `app.data`, `app.brokers`, `app.risk`, or
`app.execution`: a TradingView MCP outage must never affect the core
data/order path (Phase 01 defines no such path at all - see
docs/architecture/0006-strategy-research-lab.md).

There is no TradingView MCP SDK bundled with this repo, and this
module does not attempt to guess one - it would risk assuming a
connection protocol nobody has verified. Instead, the health check is
expressed as a `Probe`: a zero-argument callable the caller supplies
(e.g. a thin wrapper around whatever TradingView MCP client is
actually configured in the environment running the check - see
docs/research/tradingview-mcp-health-check.md for the manual
procedure). If no probe is supplied, `check_tradingview_mcp_health()`
reports `NOT_CONFIGURED` instead of attempting a network call.

Whatever the probe does, this function never raises: any exception it
raises is caught and reported as `ERROR`, so a broken or misbehaving
TradingView MCP integration can never propagate an exception into
calling code.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.core.logging import get_logger

logger = get_logger(__name__)


class TradingViewMcpStatus(StrEnum):
    CONNECTED = "connected"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class TradingViewMcpHealthResult:
    status: TradingViewMcpStatus
    checked_at: datetime
    detail: str | None = None


Probe = Callable[[], bool]


def check_tradingview_mcp_health(probe: Probe | None = None) -> TradingViewMcpHealthResult:
    """Run `probe` and report a status. Never raises."""
    checked_at = datetime.now(UTC)

    if probe is None:
        return TradingViewMcpHealthResult(
            status=TradingViewMcpStatus.NOT_CONFIGURED,
            checked_at=checked_at,
            detail=(
                "No probe configured - see "
                "docs/research/tradingview-mcp-health-check.md"
            ),
        )

    try:
        is_connected = probe()
    except Exception as exc:  # intentionally broad: this is the isolation boundary
        logger.warning(
            "tradingview_mcp.health_check_failed",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return TradingViewMcpHealthResult(
            status=TradingViewMcpStatus.ERROR, checked_at=checked_at, detail=str(exc)
        )

    if is_connected:
        return TradingViewMcpHealthResult(
            status=TradingViewMcpStatus.CONNECTED, checked_at=checked_at
        )
    return TradingViewMcpHealthResult(
        status=TradingViewMcpStatus.UNAVAILABLE, checked_at=checked_at
    )
