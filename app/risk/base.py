from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.brokers.base import OrderRequest


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str | None = None


class RiskEngine(ABC):
    """Every order must pass through a `RiskEngine` before submission.

    No concrete risk rules are implemented in Phase 00.
    """

    @abstractmethod
    def check_order(self, order: OrderRequest) -> RiskDecision:
        raise NotImplementedError
