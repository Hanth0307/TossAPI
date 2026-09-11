"""Interfaces for market data and news/disclosure providers.

Deliberately return `Any` / untyped payloads: the real response shape
of the Toss API, DART, and any news provider has not been verified yet.
Do not invent field names ahead of that verification (a concrete
provider must validate the real response and raise
`app.core.exceptions.DataValidationError` on an unexpected shape,
rather than guessing).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MarketDataProvider(ABC):
    """Source of quotes / OHLCV data for a symbol."""

    @abstractmethod
    def get_quote(self, symbol: str) -> Any:
        raise NotImplementedError


class NewsProvider(ABC):
    """Source of news headlines relevant to a symbol."""

    @abstractmethod
    def get_latest(self, symbol: str) -> Any:
        raise NotImplementedError


class DisclosureProvider(ABC):
    """Source of regulatory disclosures (e.g. DART filings) for a symbol."""

    @abstractmethod
    def get_latest(self, symbol: str) -> Any:
        raise NotImplementedError
