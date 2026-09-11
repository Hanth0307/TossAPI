from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.strategies.base import Strategy


class BacktestEngine(ABC):
    """Runs a `Strategy` against historical data and reports results.

    No concrete backtest logic is implemented in Phase 00, and no
    performance figures are assumed anywhere in this codebase.
    """

    @abstractmethod
    def run(self, strategy: Strategy, market_data: Any) -> Any:
        raise NotImplementedError
