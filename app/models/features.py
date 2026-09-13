"""Feature engineering: a fixed, versioned feature schema computed
strictly from bars with `event_time <= as_of`. See ADR 0011.

`compute_features` never looks beyond the last element of the list it
is given - it is the caller's job (`app.models.dataset.
DatasetBuilder`, via `MarketBarRepository.get_bars_as_of(..., as_of=
as_of)`) to supply an already `as_of`-gated bar list. Returns `None`
(with a reason) rather than a partially-filled vector when there isn't
enough history - a missing feature is never silently zero-filled.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.db.repositories.market_data import MarketBarRow

FEATURE_SCHEMA_VERSION = "1.0.0"

FEATURE_NAMES: tuple[str, ...] = (
    "return_1d",
    "return_5d",
    "return_10d",
    "return_20d",
    "volatility_20d",
    "volume_ratio_5d_20d",
    "price_vs_sma20",
)


@dataclass(frozen=True)
class FeatureVector:
    schema_version: str
    values: dict[str, float]

    def as_ordered_list(self) -> list[float]:
        """Fixed column order for a model matrix - always
        `FEATURE_NAMES` order, so a model trained on one schema version
        never silently reads a differently-ordered vector."""
        return [self.values[name] for name in FEATURE_NAMES]


@dataclass(frozen=True)
class FeatureComputationResult:
    vector: FeatureVector | None
    reason: str | None


def _return_over(bars: list[MarketBarRow], lookback: int) -> float | None:
    if len(bars) < lookback + 1:
        return None
    start_price = bars[-(lookback + 1)].close_price
    end_price = bars[-1].close_price
    if start_price == 0:
        return None
    return float((end_price - start_price) / start_price)


def compute_features(bars_as_of: list[MarketBarRow]) -> FeatureComputationResult:
    """`bars_as_of` must be ordered ascending by `event_time`, ending
    at (or before) `as_of`. Requires at least 21 bars (a 20-bar lookback
    plus the current bar) to fill every feature in `FEATURE_NAMES`."""
    required = 21
    if len(bars_as_of) < required:
        return FeatureComputationResult(
            vector=None, reason=f"need {required} bars, got {len(bars_as_of)}"
        )

    raw_return_1d = _return_over(bars_as_of, 1)
    raw_return_5d = _return_over(bars_as_of, 5)
    raw_return_10d = _return_over(bars_as_of, 10)
    raw_return_20d = _return_over(bars_as_of, 20)
    if (
        raw_return_1d is None
        or raw_return_5d is None
        or raw_return_10d is None
        or raw_return_20d is None
    ):
        return FeatureComputationResult(vector=None, reason="a return lookback had a zero price")
    return_1d, return_5d, return_10d, return_20d = (
        raw_return_1d, raw_return_5d, raw_return_10d, raw_return_20d,
    )

    window_20 = bars_as_of[-20:]
    daily_returns = []
    for previous, current in zip(window_20, window_20[1:], strict=False):
        if previous.close_price == 0:
            continue
        daily_return = (current.close_price - previous.close_price) / previous.close_price
        daily_returns.append(float(daily_return))
    if len(daily_returns) < 2:
        return FeatureComputationResult(
            vector=None, reason="fewer than 2 daily returns available for volatility_20d"
        )
    volatility_20d = statistics.pstdev(daily_returns)

    volumes_5 = [float(b.volume) for b in bars_as_of[-5:]]
    volumes_20 = [float(b.volume) for b in window_20]
    avg_volume_20 = sum(volumes_20) / len(volumes_20)
    if avg_volume_20 == 0:
        return FeatureComputationResult(vector=None, reason="average 20-bar volume is zero")
    volume_ratio_5d_20d = (sum(volumes_5) / len(volumes_5)) / avg_volume_20

    closes_20 = [float(b.close_price) for b in window_20]
    sma_20 = sum(closes_20) / len(closes_20)
    if sma_20 == 0:
        return FeatureComputationResult(vector=None, reason="20-bar SMA is zero")
    price_vs_sma20 = float(bars_as_of[-1].close_price) / sma_20 - 1.0

    values = {
        "return_1d": return_1d,
        "return_5d": return_5d,
        "return_10d": return_10d,
        "return_20d": return_20d,
        "volatility_20d": volatility_20d,
        "volume_ratio_5d_20d": volume_ratio_5d_20d,
        "price_vs_sma20": price_vs_sma20,
    }
    vector = FeatureVector(schema_version=FEATURE_SCHEMA_VERSION, values=values)
    return FeatureComputationResult(vector=vector, reason=None)
