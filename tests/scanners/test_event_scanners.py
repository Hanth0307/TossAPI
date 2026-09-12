"""Fixed-fixture detected/not-detected reproduction for every
`EventScannerPlugin` - no database, per `app/scanners/events.py`'s
module docstring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.db.repositories.disclosure import DisclosureEventRow
from app.db.repositories.market_data import MarketBarRow, OrderBookSnapshotRow
from app.db.repositories.news import NewsEventRow
from app.scanners.events import (
    AbnormalVolumeEventScanner,
    DisclosureOccurrenceEventScanner,
    EventScanInput,
    NewsOccurrenceEventScanner,
    OrderbookImbalanceEventScanner,
    PriceGapEventScanner,
    VolatilitySpikeEventScanner,
)


def _bar(
    *, open_: str, high: str, low: str, close: str, volume: str, event_time: datetime
) -> MarketBarRow:
    return MarketBarRow(
        instrument_id=1,
        timeframe="1d",
        event_time=event_time,
        available_at=event_time,
        ingested_at=event_time,
        revision=1,
        open_price=Decimal(open_),
        high_price=Decimal(high),
        low_price=Decimal(low),
        close_price=Decimal(close),
        volume=Decimal(volume),
        currency="KRW",
        source="toss_openapi",
    )


def _empty_input(bars: list[MarketBarRow]) -> EventScanInput:
    return EventScanInput(bars=bars, news=[], disclosures=[], orderbook=None)


def test_price_gap_scanner_detects_large_gap() -> None:
    bars = [
        _bar(
            open_="100", high="100", low="100", close="100", volume="10",
            event_time=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        _bar(
            open_="110", high="110", low="110", close="110", volume="10",
            event_time=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    ]
    scanner = PriceGapEventScanner(min_gap_ratio=Decimal("0.05"))
    detection = scanner.detect(_empty_input(bars))
    assert detection.detected is True
    assert detection.observed_value == Decimal("0.1")


def test_price_gap_scanner_does_not_detect_small_gap() -> None:
    bars = [
        _bar(
            open_="100", high="100", low="100", close="100", volume="10",
            event_time=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        _bar(
            open_="101", high="101", low="101", close="101", volume="10",
            event_time=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    ]
    scanner = PriceGapEventScanner(min_gap_ratio=Decimal("0.05"))
    detection = scanner.detect(_empty_input(bars))
    assert detection.detected is False
    assert detection.reason is not None


def test_abnormal_volume_scanner_detects_spike() -> None:
    bars = [
        _bar(
            open_="100", high="100", low="100", close="100", volume="1000",
            event_time=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        _bar(
            open_="100", high="100", low="100", close="100", volume="1000",
            event_time=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        _bar(
            open_="100", high="100", low="100", close="100", volume="10000",
            event_time=datetime(2026, 1, 3, tzinfo=UTC),
        ),
    ]
    scanner = AbnormalVolumeEventScanner(min_volume_multiple=Decimal("3"))
    detection = scanner.detect(_empty_input(bars))
    assert detection.detected is True
    assert detection.observed_value == Decimal("10")


def test_abnormal_volume_scanner_does_not_detect_normal_volume() -> None:
    bars = [
        _bar(
            open_="100", high="100", low="100", close="100", volume="1000",
            event_time=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        _bar(
            open_="100", high="100", low="100", close="100", volume="1100",
            event_time=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    ]
    scanner = AbnormalVolumeEventScanner(min_volume_multiple=Decimal("3"))
    detection = scanner.detect(_empty_input(bars))
    assert detection.detected is False


def test_volatility_spike_scanner_detects_wide_range() -> None:
    bars = [
        _bar(
            open_="100", high="120", low="80", close="100", volume="10",
            event_time=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    scanner = VolatilitySpikeEventScanner(min_range_ratio=Decimal("0.1"))
    detection = scanner.detect(_empty_input(bars))
    assert detection.detected is True


def test_volatility_spike_scanner_does_not_detect_narrow_range() -> None:
    bars = [
        _bar(
            open_="100", high="101", low="99", close="100", volume="10",
            event_time=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    scanner = VolatilitySpikeEventScanner(min_range_ratio=Decimal("0.5"))
    detection = scanner.detect(_empty_input(bars))
    assert detection.detected is False


def _news(event_time: datetime) -> NewsEventRow:
    return NewsEventRow(
        source="mock_news",
        external_id=f"n-{event_time.isoformat()}",
        event_time=event_time,
        available_at=event_time,
        ingested_at=event_time,
        revision=1,
        headline="headline",
        body=None,
        related_symbols=["005930"],
    )


def test_news_occurrence_scanner_detects_enough_articles() -> None:
    news = [_news(datetime(2026, 1, 1, tzinfo=UTC)), _news(datetime(2026, 1, 2, tzinfo=UTC))]
    scanner = NewsOccurrenceEventScanner(min_count=2)
    detection = scanner.detect(EventScanInput(bars=[], news=news, disclosures=[], orderbook=None))
    assert detection.detected is True
    assert detection.observed_value == 2


def test_news_occurrence_scanner_does_not_detect_too_few_articles() -> None:
    news = [_news(datetime(2026, 1, 1, tzinfo=UTC))]
    scanner = NewsOccurrenceEventScanner(min_count=2)
    detection = scanner.detect(EventScanInput(bars=[], news=news, disclosures=[], orderbook=None))
    assert detection.detected is False


def _disclosure(event_time: datetime) -> DisclosureEventRow:
    return DisclosureEventRow(
        source="mock_dart",
        external_id=f"d-{event_time.isoformat()}",
        instrument_id=1,
        event_time=event_time,
        available_at=event_time,
        ingested_at=event_time,
        revision=1,
        title="filing",
        filing_type=None,
    )


def test_disclosure_occurrence_scanner_detects_enough_filings() -> None:
    disclosures = [_disclosure(datetime(2026, 1, 1, tzinfo=UTC))]
    scanner = DisclosureOccurrenceEventScanner(min_count=1)
    detection = scanner.detect(
        EventScanInput(bars=[], news=[], disclosures=disclosures, orderbook=None)
    )
    assert detection.detected is True


def test_disclosure_occurrence_scanner_does_not_detect_no_filings() -> None:
    scanner = DisclosureOccurrenceEventScanner(min_count=1)
    detection = scanner.detect(EventScanInput(bars=[], news=[], disclosures=[], orderbook=None))
    assert detection.detected is False


def _orderbook(bid_volume: str, ask_volume: str) -> OrderBookSnapshotRow:
    return OrderBookSnapshotRow(
        instrument_id=1,
        event_time=datetime(2026, 1, 1, tzinfo=UTC),
        available_at=datetime(2026, 1, 1, tzinfo=UTC),
        ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
        currency="KRW",
        bids=[{"price": "100", "volume": bid_volume}],
        asks=[{"price": "101", "volume": ask_volume}],
        source="toss_openapi",
    )


def test_orderbook_imbalance_scanner_detects_strong_imbalance() -> None:
    orderbook = _orderbook(bid_volume="900", ask_volume="100")
    scanner = OrderbookImbalanceEventScanner(min_imbalance_ratio=Decimal("0.5"))
    detection = scanner.detect(
        EventScanInput(bars=[], news=[], disclosures=[], orderbook=orderbook)
    )
    assert detection.detected is True
    assert detection.observed_value == Decimal("0.8")


def test_orderbook_imbalance_scanner_does_not_detect_balanced_book() -> None:
    orderbook = _orderbook(bid_volume="510", ask_volume="490")
    scanner = OrderbookImbalanceEventScanner(min_imbalance_ratio=Decimal("0.5"))
    detection = scanner.detect(
        EventScanInput(bars=[], news=[], disclosures=[], orderbook=orderbook)
    )
    assert detection.detected is False


def test_orderbook_imbalance_scanner_does_not_detect_when_no_orderbook() -> None:
    scanner = OrderbookImbalanceEventScanner(min_imbalance_ratio=Decimal("0.5"))
    detection = scanner.detect(EventScanInput(bars=[], news=[], disclosures=[], orderbook=None))
    assert detection.detected is False


def test_market_specific_scanner_field_is_carried_through() -> None:
    scanner = PriceGapEventScanner(min_gap_ratio=Decimal("0.05"), market="KR")
    bars = [
        _bar(
            open_="100", high="100", low="100", close="100", volume="10",
            event_time=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        _bar(
            open_="110", high="110", low="110", close="110", volume="10",
            event_time=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    ]
    detection = scanner.detect(_empty_input(bars))
    assert detection.market == "KR"
