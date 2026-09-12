"""ScannerPipeline: wires Market -> Universe Filter -> Event Scanner ->
Strategy Scanner -> Candidate together against `app.db.repositories`.

Staged gating, cheapest/most-selective first:

1. **Market** - `InstrumentRepository.list_all()` (optionally narrowed
   to one exchange).
2. **Universe Filter** - always computed for every instrument, from
   bars already fetched `as_of`-gated. An instrument that fails any
   filter gets a `Candidate` immediately (`qualified=False`) - news,
   disclosures, orderbook and Strategy Scanner conditions are never
   fetched/evaluated for it, since they cannot change a universe
   failure.
3. **Event Scanner** - only run for instruments that passed the
   Universe Filter. Only plugins whose `market` is `None` (market-
   agnostic) or matches the instrument's `exchange` run for it, so
   Korean/US-specific rules stay separate per the phase requirement.
   An instrument with no triggering event (and at least one configured
   event scanner) also gets an immediate `Candidate` - the Strategy
   Scanner never runs without something to react to. If no event
   scanners are configured at all, this stage is a pass-through (there
   is nothing to gate on).
4. **Strategy Scanner** - only run when an event triggered (or no event
   scanners are configured). Builds a `FeatureSet` from the same
   `as_of`-gated bars/detections and evaluates the optional
   `StrategyRuleSet`.

Every fetch this pipeline makes goes through an `app.db.repositories`
`as_of`-gated method - the pipeline itself never queries a table
directly, so it inherits the leak-free guarantee proven in
`tests/db/test_point_in_time_correction.py` (ADR 0008/0009).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.repositories.disclosure import DisclosureRepository
from app.db.repositories.market_data import (
    InstrumentRepository,
    InstrumentRow,
    MarketBarRepository,
    MarketBarRow,
    OrderbookRepository,
)
from app.db.repositories.news import NewsRepository
from app.scanners.candidate import Candidate
from app.scanners.events import EventDetection, EventScanInput, EventScannerPlugin
from app.scanners.features import FeatureSet
from app.scanners.strategy_rules import StrategyRuleSet, StrategyScanner
from app.scanners.universe import UniverseFilter, UniverseFilterInput


@dataclass(frozen=True)
class PipelineConfig:
    timeframe: str
    lookback_days: int
    news_lookback_days: int
    disclosure_lookback_days: int
    exchange: str | None = None


class ScannerPipeline:
    def __init__(
        self,
        session: Session,
        *,
        config: PipelineConfig,
        universe_filters: Sequence[UniverseFilter],
        event_scanners: Sequence[EventScannerPlugin],
        strategy_rule_set: StrategyRuleSet | None,
        data_source: str,
    ) -> None:
        self._config = config
        self._universe_filters = universe_filters
        self._event_scanners = event_scanners
        self._strategy_rule_set = strategy_rule_set
        self._data_source = data_source
        self._instruments = InstrumentRepository(session)
        self._bars = MarketBarRepository(session)
        self._news = NewsRepository(session)
        self._disclosures = DisclosureRepository(session)
        self._orderbook = OrderbookRepository(session)
        self._strategy_scanner = StrategyScanner()

    def scan(self, *, as_of: datetime) -> list[Candidate]:
        instruments = self._instruments.list_all(exchange=self._config.exchange)
        return [self._scan_instrument(instrument, as_of=as_of) for instrument in instruments]

    def _scan_instrument(self, instrument: InstrumentRow, *, as_of: datetime) -> Candidate:
        bars = self._bars.get_bars_as_of(
            instrument_id=instrument.id,
            timeframe=self._config.timeframe,
            start=as_of - timedelta(days=self._config.lookback_days),
            end=as_of,
            as_of=as_of,
        )
        universe_input = UniverseFilterInput(instrument=instrument, recent_bars=bars)
        universe_results = [f.evaluate(universe_input) for f in self._universe_filters]
        passed_universe = all(result.passed for result in universe_results)

        if not passed_universe:
            return Candidate(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                exchange=instrument.exchange,
                as_of=as_of,
                data_source=self._data_source,
                universe_results=universe_results,
                event_detections=[],
                strategy_result=None,
                qualified=False,
                generated_at=as_of,
            )

        news = self._news.get_news_as_of(
            start=as_of - timedelta(days=self._config.news_lookback_days),
            end=as_of,
            as_of=as_of,
            symbol=instrument.symbol,
        )
        disclosures = self._disclosures.get_disclosures_as_of(
            start=as_of - timedelta(days=self._config.disclosure_lookback_days),
            end=as_of,
            as_of=as_of,
            instrument_id=instrument.id,
        )
        orderbook = self._orderbook.get_latest_as_of(instrument_id=instrument.id, as_of=as_of)
        event_input = EventScanInput(
            bars=bars, news=news, disclosures=disclosures, orderbook=orderbook
        )
        applicable_scanners = [
            scanner
            for scanner in self._event_scanners
            if scanner.market is None or scanner.market == instrument.exchange
        ]
        event_detections = [scanner.detect(event_input) for scanner in applicable_scanners]
        has_triggering_event = (
            any(detection.detected for detection in event_detections)
            if applicable_scanners
            else True
        )

        if not has_triggering_event:
            return Candidate(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                exchange=instrument.exchange,
                as_of=as_of,
                data_source=self._data_source,
                universe_results=universe_results,
                event_detections=event_detections,
                strategy_result=None,
                qualified=False,
                generated_at=as_of,
            )

        feature_set = self._build_feature_set(
            instrument, bars=bars, event_detections=event_detections, as_of=as_of
        )
        strategy_result = None
        if self._strategy_rule_set is not None:
            strategy_result = self._strategy_scanner.evaluate(
                self._strategy_rule_set, feature_set=feature_set
            )

        qualified = has_triggering_event and (
            strategy_result.passed if strategy_result is not None else True
        )
        return Candidate(
            instrument_id=instrument.id,
            symbol=instrument.symbol,
            exchange=instrument.exchange,
            as_of=as_of,
            data_source=self._data_source,
            universe_results=universe_results,
            event_detections=event_detections,
            strategy_result=strategy_result,
            qualified=qualified,
            generated_at=as_of,
        )

    def _build_feature_set(
        self,
        instrument: InstrumentRow,
        *,
        bars: list[MarketBarRow],
        event_detections: list[EventDetection],
        as_of: datetime,
    ) -> FeatureSet:
        values: dict[str, Decimal] = {}
        if bars:
            latest = bars[-1]
            values["close_price"] = latest.close_price
            values["volume"] = latest.volume
        for detection in event_detections:
            if isinstance(detection.observed_value, Decimal):
                values[detection.event_name] = detection.observed_value
        return FeatureSet(
            instrument_symbol=instrument.symbol,
            as_of=as_of,
            data_source=self._data_source,
            values=values,
        )
