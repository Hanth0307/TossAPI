"""Market Regime: pure logic over already `as_of`-fetched benchmark
bars (and optional cross-sectional breadth counts) - never queries a
database itself, so it carries no as_of-correctness burden of its own:
whatever window the caller hands it is the only window it ever looks
at (see `tests/regime/test_classifier.py`). `app.regime.provider`
wraps this with the `as_of`-gated repository read.

Every threshold is a required constructor argument, never hardcoded,
matching `app.scanners.universe`'s discipline.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.db.repositories.market_data import MarketBarRow


class TrendState(StrEnum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    SIDEWAYS = "sideways"
    UNKNOWN = "unknown"


class VolatilityLevel(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    UNKNOWN = "unknown"


class BreadthState(StrEnum):
    EXPANDING = "expanding"
    CONTRACTING = "contracting"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RegimeInput:
    bars: list[MarketBarRow]
    advancing_count: int | None = None
    declining_count: int | None = None


@dataclass(frozen=True)
class RegimeAssessment:
    as_of: datetime
    trend: TrendState
    volatility_level: VolatilityLevel
    breadth: BreadthState
    observed_return: Decimal | None
    observed_volatility: Decimal | None
    observed_breadth_ratio: Decimal | None
    reasons: list[str] = field(default_factory=list)


def _daily_returns(bars: list[MarketBarRow]) -> list[Decimal]:
    returns = []
    for previous, current in zip(bars, bars[1:], strict=False):
        if previous.close_price == 0:
            continue
        returns.append((current.close_price - previous.close_price) / previous.close_price)
    return returns


@dataclass(frozen=True)
class RegimeClassifier:
    trend_lookback_bars: int
    trend_up_threshold: Decimal
    trend_down_threshold: Decimal
    volatility_lookback_bars: int
    high_volatility_threshold: Decimal
    low_volatility_threshold: Decimal
    breadth_expanding_threshold: Decimal
    breadth_contracting_threshold: Decimal

    def classify(self, data: RegimeInput, *, as_of: datetime) -> RegimeAssessment:
        reasons: list[str] = []

        trend, observed_return = self._classify_trend(data.bars, reasons)
        volatility_level, observed_volatility = self._classify_volatility(data.bars, reasons)
        breadth, observed_breadth_ratio = self._classify_breadth(
            data.advancing_count, data.declining_count, reasons
        )

        return RegimeAssessment(
            as_of=as_of,
            trend=trend,
            volatility_level=volatility_level,
            breadth=breadth,
            observed_return=observed_return,
            observed_volatility=observed_volatility,
            observed_breadth_ratio=observed_breadth_ratio,
            reasons=reasons,
        )

    def _classify_trend(
        self, bars: list[MarketBarRow], reasons: list[str]
    ) -> tuple[TrendState, Decimal | None]:
        if len(bars) < self.trend_lookback_bars + 1:
            reasons.append(
                f"trend: only {len(bars)} bars available, need "
                f"{self.trend_lookback_bars + 1}"
            )
            return TrendState.UNKNOWN, None

        window = bars[-(self.trend_lookback_bars + 1) :]
        start_price, end_price = window[0].close_price, window[-1].close_price
        if start_price == 0:
            reasons.append("trend: window start close_price is zero")
            return TrendState.UNKNOWN, None

        observed_return = (end_price - start_price) / start_price
        if observed_return >= self.trend_up_threshold:
            reasons.append(f"trend: return {observed_return} >= {self.trend_up_threshold}")
            return TrendState.UPTREND, observed_return
        if observed_return <= self.trend_down_threshold:
            reasons.append(f"trend: return {observed_return} <= {self.trend_down_threshold}")
            return TrendState.DOWNTREND, observed_return
        reasons.append(
            f"trend: return {observed_return} within "
            f"[{self.trend_down_threshold}, {self.trend_up_threshold}]"
        )
        return TrendState.SIDEWAYS, observed_return

    def _classify_volatility(
        self, bars: list[MarketBarRow], reasons: list[str]
    ) -> tuple[VolatilityLevel, Decimal | None]:
        window = bars[-(self.volatility_lookback_bars + 1) :]
        returns = _daily_returns(window)
        if len(returns) < 2:
            reasons.append(
                f"volatility: only {len(returns)} return observations available, need 2"
            )
            return VolatilityLevel.UNKNOWN, None

        observed_volatility = Decimal(str(statistics.pstdev([float(r) for r in returns])))
        if observed_volatility >= self.high_volatility_threshold:
            reasons.append(
                f"volatility: {observed_volatility} >= {self.high_volatility_threshold}"
            )
            return VolatilityLevel.HIGH, observed_volatility
        if observed_volatility <= self.low_volatility_threshold:
            reasons.append(
                f"volatility: {observed_volatility} <= {self.low_volatility_threshold}"
            )
            return VolatilityLevel.LOW, observed_volatility
        reasons.append(
            f"volatility: {observed_volatility} within "
            f"[{self.low_volatility_threshold}, {self.high_volatility_threshold}]"
        )
        return VolatilityLevel.NORMAL, observed_volatility

    def _classify_breadth(
        self, advancing_count: int | None, declining_count: int | None, reasons: list[str]
    ) -> tuple[BreadthState, Decimal | None]:
        if advancing_count is None or declining_count is None:
            reasons.append("breadth: advancing/declining counts not provided")
            return BreadthState.UNKNOWN, None
        total = advancing_count + declining_count
        if total == 0:
            reasons.append("breadth: advancing + declining count is zero")
            return BreadthState.UNKNOWN, None

        ratio = Decimal(advancing_count) / Decimal(total)
        if ratio >= self.breadth_expanding_threshold:
            reasons.append(f"breadth: ratio {ratio} >= {self.breadth_expanding_threshold}")
            return BreadthState.EXPANDING, ratio
        if ratio <= self.breadth_contracting_threshold:
            reasons.append(f"breadth: ratio {ratio} <= {self.breadth_contracting_threshold}")
            return BreadthState.CONTRACTING, ratio
        reasons.append(
            f"breadth: ratio {ratio} within "
            f"[{self.breadth_contracting_threshold}, {self.breadth_expanding_threshold}]"
        )
        return BreadthState.NEUTRAL, ratio
