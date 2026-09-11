from __future__ import annotations

from app.research.tradingview_mcp import (
    TradingViewMcpStatus,
    check_tradingview_mcp_health,
)


def test_no_probe_reports_not_configured() -> None:
    result = check_tradingview_mcp_health()
    assert result.status == TradingViewMcpStatus.NOT_CONFIGURED


def test_probe_returning_true_reports_connected() -> None:
    result = check_tradingview_mcp_health(probe=lambda: True)
    assert result.status == TradingViewMcpStatus.CONNECTED


def test_probe_returning_false_reports_unavailable() -> None:
    result = check_tradingview_mcp_health(probe=lambda: False)
    assert result.status == TradingViewMcpStatus.UNAVAILABLE


def test_probe_raising_reports_error_without_propagating() -> None:
    def boom() -> bool:
        raise RuntimeError("connection refused")

    result = check_tradingview_mcp_health(probe=boom)

    assert result.status == TradingViewMcpStatus.ERROR
    assert result.detail == "connection refused"


def test_result_always_carries_a_checked_at_timestamp() -> None:
    result = check_tradingview_mcp_health()
    assert result.checked_at is not None
