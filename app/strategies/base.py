from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Strategy(ABC):
    """Generates order intents from market data (and optionally signals).

    No concrete strategy is implemented in Phase 00. Implementations
    must not hardcode or assume any expected return/performance
    figures.
    """

    @abstractmethod
    def generate_signals(self, market_data: Any) -> Any:
        raise NotImplementedError
