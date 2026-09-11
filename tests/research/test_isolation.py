"""Proves the TradingView MCP dependency is actually isolated.

`app.research.registry` and `app.research.models` have no import edge
to `app.research.tradingview_mcp` at all, so a TradingView MCP outage
- simulated below by a probe that raises - can never affect Strategy
Registry reads/writes. This is the concrete check for the "TradingView
MCP 장애가 본 시스템 데이터/주문 경로에 영향을 주지 않도록" requirement.
"""

from __future__ import annotations

from pathlib import Path

from app.research.models import StrategySource, StrategySpec
from app.research.registry import StrategyRegistry
from app.research.tradingview_mcp import TradingViewMcpStatus, check_tradingview_mcp_health


def _simulated_outage() -> bool:
    raise ConnectionError("TradingView MCP is unreachable")


def test_tradingview_outage_is_reported_without_raising() -> None:
    result = check_tradingview_mcp_health(probe=_simulated_outage)
    assert result.status == TradingViewMcpStatus.ERROR


def test_registry_round_trip_is_unaffected_by_a_tradingview_outage(tmp_path: Path) -> None:
    # Confirm the outage above happened, then prove the registry -
    # which never imports tradingview_mcp - works regardless.
    outage = check_tradingview_mcp_health(probe=_simulated_outage)
    assert outage.status == TradingViewMcpStatus.ERROR

    registry = StrategyRegistry(base_dir=tmp_path)
    spec = StrategySpec(
        strategy_id="STR-ISO-001",
        name="Isolation smoke test",
        version="0.1.0",
        source=StrategySource.MANUAL,
        hypothesis="Registry works even when TradingView MCP is down.",
        universe=["KOSPI:005930"],
        timeframe="1D",
        entry_rules=["placeholder entry rule"],
        exit_rules=["placeholder exit rule"],
        risk_assumptions=["placeholder risk assumption"],
    )

    registry.save(spec)
    reloaded = registry.load(spec.strategy_id, spec.version)

    assert reloaded == spec
