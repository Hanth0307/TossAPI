"""Event Scanner: plugin-based detectors for price gaps, abnormal
volume, volatility spikes, news/disclosure occurrence, and orderbook
imbalance.

Pure logic - every plugin operates on data already fetched (and
already `as_of`-filtered) by the caller, typically
`app.scanners.pipeline.ScannerPipeline`. No plugin here queries a
database or an external API itself, so each one is testable with a
fixed fixture - see `tests/scanners/test_event_scanners.py`.

Each plugin declares a `market: str | None` ("KR"/"US"/... or `None`
for a market-agnostic rule) so `app.scanners.pipeline.ScannerPipeline`
can apply Korean- and US-specific event rules separately, as required:
a plugin whose `market` does not match the instrument's exchange market
is simply not run for that instrument.

Numeric thresholds are always constructor arguments, never hardcoded,
so the same plugin class can be reused with different limits per
strategy/market/run.

**No sentiment/quality score is invented here.** The news/disclosure
plugins below detect existence/count only ("did N events happen in the
window") - there is no AI/sentiment model in this codebase yet, and
none is fabricated in its place.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.db.repositories.disclosure import DisclosureEventRow
from app.db.repositories.market_data import MarketBarRow, OrderBookSnapshotRow
from app.db.repositories.news import NewsEventRow


@dataclass(frozen=True)
class EventScanInput:
    bars: list[MarketBarRow]
    news: list[NewsEventRow]
    disclosures: list[DisclosureEventRow]
    orderbook: OrderBookSnapshotRow | None


@dataclass(frozen=True)
class EventDetection:
    event_name: str
    detected: bool
    observed_value: object
    threshold: object | None
    market: str | None
    reason: str | None


class EventScannerPlugin(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def market(self) -> str | None: ...

    def detect(self, data: EventScanInput) -> EventDetection: ...


@dataclass(frozen=True)
class PriceGapEventScanner:
    """Detects a gap between the previous bar's close and the latest
    bar's open at least `min_gap_ratio` of the previous close (e.g.
    `Decimal("0.03")` for a 3% gap), in either direction.
    """

    min_gap_ratio: Decimal
    market: str | None = None
    name: str = "price_gap"

    def detect(self, data: EventScanInput) -> EventDetection:
        if len(data.bars) < 2:
            return EventDetection(
                self.name, False, None, self.min_gap_ratio, self.market, "fewer than 2 bars"
            )
        previous, latest = data.bars[-2], data.bars[-1]
        if previous.close_price == 0:
            return EventDetection(
                self.name, False, None, self.min_gap_ratio, self.market, "previous close is zero"
            )
        gap_ratio = abs(latest.open_price - previous.close_price) / previous.close_price
        detected = gap_ratio >= self.min_gap_ratio
        reason = None if detected else f"gap ratio {gap_ratio} < {self.min_gap_ratio}"
        return EventDetection(
            self.name, detected, gap_ratio, self.min_gap_ratio, self.market, reason
        )


@dataclass(frozen=True)
class AbnormalVolumeEventScanner:
    """Detects the latest bar's volume being at least
    `min_volume_multiple` times the average volume of the preceding
    bars (excluding the latest one)."""

    min_volume_multiple: Decimal
    market: str | None = None
    name: str = "abnormal_volume"

    def detect(self, data: EventScanInput) -> EventDetection:
        if len(data.bars) < 2:
            return EventDetection(
                self.name, False, None, self.min_volume_multiple, self.market, "fewer than 2 bars"
            )
        *history, latest = data.bars
        avg_volume = sum((bar.volume for bar in history), Decimal(0)) / len(history)
        if avg_volume == 0:
            return EventDetection(
                self.name,
                False,
                None,
                self.min_volume_multiple,
                self.market,
                "average historical volume is zero",
            )
        multiple = latest.volume / avg_volume
        detected = multiple >= self.min_volume_multiple
        reason = None if detected else f"volume multiple {multiple} < {self.min_volume_multiple}"
        return EventDetection(
            self.name, detected, multiple, self.min_volume_multiple, self.market, reason
        )


@dataclass(frozen=True)
class VolatilitySpikeEventScanner:
    """Detects the latest bar's intrabar range (`high - low`, as a
    ratio of its close_price) being at least `min_range_ratio`."""

    min_range_ratio: Decimal
    market: str | None = None
    name: str = "volatility_spike"

    def detect(self, data: EventScanInput) -> EventDetection:
        if not data.bars:
            return EventDetection(
                self.name, False, None, self.min_range_ratio, self.market, "no bars available"
            )
        latest = data.bars[-1]
        if latest.close_price == 0:
            return EventDetection(
                self.name, False, None, self.min_range_ratio, self.market, "close price is zero"
            )
        range_ratio = (latest.high_price - latest.low_price) / latest.close_price
        detected = range_ratio >= self.min_range_ratio
        reason = None if detected else f"range ratio {range_ratio} < {self.min_range_ratio}"
        return EventDetection(
            self.name, detected, range_ratio, self.min_range_ratio, self.market, reason
        )


@dataclass(frozen=True)
class NewsOccurrenceEventScanner:
    """Detects at least `min_count` news items in the already
    as_of/window-filtered `data.news` list. Existence/count-based only
    - no sentiment or quality score is computed or invented."""

    min_count: int
    market: str | None = None
    name: str = "news_occurrence"

    def detect(self, data: EventScanInput) -> EventDetection:
        count = len(data.news)
        detected = count >= self.min_count
        reason = None if detected else f"news count {count} < {self.min_count}"
        return EventDetection(self.name, detected, count, self.min_count, self.market, reason)


@dataclass(frozen=True)
class DisclosureOccurrenceEventScanner:
    """Detects at least `min_count` disclosure items in the already
    as_of/window-filtered `data.disclosures` list. Existence/count-
    based only - no sentiment or quality score is computed or
    invented."""

    min_count: int
    market: str | None = None
    name: str = "disclosure_occurrence"

    def detect(self, data: EventScanInput) -> EventDetection:
        count = len(data.disclosures)
        detected = count >= self.min_count
        reason = None if detected else f"disclosure count {count} < {self.min_count}"
        return EventDetection(self.name, detected, count, self.min_count, self.market, reason)


@dataclass(frozen=True)
class OrderbookImbalanceEventScanner:
    """Detects a bid/ask total-volume imbalance ("수급 변화") of at
    least `min_imbalance_ratio` (`abs(bid_volume - ask_volume) /
    (bid_volume + ask_volume)`)."""

    min_imbalance_ratio: Decimal
    market: str | None = None
    name: str = "orderbook_imbalance"

    def detect(self, data: EventScanInput) -> EventDetection:
        if data.orderbook is None:
            return EventDetection(
                self.name,
                False,
                None,
                self.min_imbalance_ratio,
                self.market,
                "no orderbook snapshot available",
            )
        bid_volume = sum(
            (Decimal(str(level.get("volume", 0))) for level in data.orderbook.bids), Decimal(0)
        )
        ask_volume = sum(
            (Decimal(str(level.get("volume", 0))) for level in data.orderbook.asks), Decimal(0)
        )
        total = bid_volume + ask_volume
        if total == 0:
            return EventDetection(
                self.name, False, None, self.min_imbalance_ratio, self.market, "no orderbook depth"
            )
        imbalance_ratio = abs(bid_volume - ask_volume) / total
        detected = imbalance_ratio >= self.min_imbalance_ratio
        reason = (
            None if detected else f"imbalance ratio {imbalance_ratio} < {self.min_imbalance_ratio}"
        )
        return EventDetection(
            self.name, detected, imbalance_ratio, self.min_imbalance_ratio, self.market, reason
        )
