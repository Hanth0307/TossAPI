"""Uses a fake `MarketDataAdapter` double (not a real Toss call) to
prove `MarketBarIngestor` correctly bridges `app.toss`'s normalized
`CandleSeries` into `app.db`'s `market_bars` table.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.db.repositories.market_data import InstrumentRepository, MarketBarRepository
from app.db.schema import market_bars
from app.ingest.market_data_ingestor import MarketBarIngestor
from app.toss.market_data import CandleInterval
from app.toss.models import Candle, CandleSeries, RecordMetadata

NOW = datetime(2026, 3, 25, 9, 0, tzinfo=UTC)


class _FakeMarketDataAdapter:
    def get_candles(self, symbol: str, interval, count: int) -> CandleSeries:
        candle = Candle(
            timestamp=NOW,
            open_price=Decimal("100"),
            high_price=Decimal("110"),
            low_price=Decimal("95"),
            close_price=Decimal("105"),
            volume=Decimal("1000"),
            currency="KRW",
        )
        return CandleSeries(
            metadata=RecordMetadata(
                source="toss_openapi", event_time=None, available_at=NOW, ingested_at=NOW
            ),
            symbol=symbol,
            interval=interval.value if hasattr(interval, "value") else str(interval),
            candles=[candle],
            next_before=None,
        )


def test_ingest_candles_writes_a_normalized_bar_and_is_idempotent(
    migrated_schema, db_session
) -> None:
    ingestor = MarketBarIngestor(
        _FakeMarketDataAdapter(),  # type: ignore[arg-type]
        InstrumentRepository(db_session),
        MarketBarRepository(db_session),
        clock=lambda: NOW,
    )

    first = ingestor.ingest_candles(symbol="005930", interval=CandleInterval.ONE_DAY, count=1)
    second = ingestor.ingest_candles(symbol="005930", interval=CandleInterval.ONE_DAY, count=1)

    assert first.attempted == 1
    assert second.attempted == 1

    count = db_session.execute(select(func.count()).select_from(market_bars)).scalar_one()
    assert count == 1

    instrument = InstrumentRepository(db_session).get_by_symbol(exchange="KRX", symbol="005930")
    assert instrument is not None
    bars = MarketBarRepository(db_session).get_bars_as_of(
        instrument_id=instrument.id,
        timeframe="1d",
        start=NOW.replace(hour=0),
        end=NOW.replace(hour=23),
        as_of=NOW,
    )
    assert len(bars) == 1
    assert bars[0].close_price == Decimal("105")
