from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SignalModel(ABC):
    """Turns input features into a trading signal / prediction.

    No concrete model (rule-based, statistical, or ML) is implemented
    in Phase 00.
    """

    @abstractmethod
    def predict(self, features: Any) -> Any:
        raise NotImplementedError
