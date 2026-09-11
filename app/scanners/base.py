from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Scanner(ABC):
    """Produces a ranked/filtered list of candidate symbols.

    No concrete scanning criteria are implemented in Phase 00.
    """

    @abstractmethod
    def scan(self) -> list[Any]:
        raise NotImplementedError
