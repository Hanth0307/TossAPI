"""Pulls candles from `app.toss.market_data.MarketDataAdapter` (Phase
02, read-only) and writes them through `app.db.repositories` (Phase
03) - the concrete example of `app.ingest` sitting above both.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.db.repositories.market_data import InstrumentRepository, MarketBarRepository
from app.ingest.results import IngestResult
from app.toss.market_data import CandleInterval, MarketDataAdapter


class MarketBarIngestor:
    def __init__(
        self,
        market_data_adapter: MarketDataAdapter,
        instrument_repository: InstrumentRepository,
        bar_repository: MarketBarRepository,
        *,
        exchange: str = "KRX",
        source: str = "toss_openapi",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._market_data = market_data_adapter
        self._instruments = instrument_repository
        self._bars = bar_repository
        self._exchange = exchange
        self._source = source
        self._clock = clock

    def ingest_candles(
        self, *, symbol: str, interval: CandleInterval, count: int
    ) -> IngestResult:
        instrument = self._instruments.get_or_create(
            exchange=self._exchange, symbol=symbol, source=self._source
        )
        series = self._market_data.get_candles(symbol, interval, count)
        now = self._clock()

        rows = [
            {
                "instrument_id": instrument.id,
                "timeframe": series.interval,
                "event_time": candle.timestamp,
                "available_at": now,
                "ingested_at": now,
                "open_price": candle.open_price,
                "high_price": candle.high_price,
                "low_price": candle.low_price,
                "close_price": candle.close_price,
                "volume": candle.volume,
                "currency": candle.currency,
                "source": self._source,
            }
            for candle in series.candles
        ]
        upserted = self._bars.upsert_bars(rows)
        return IngestResult(source=self._source, attempted=len(rows), upserted=upserted)
