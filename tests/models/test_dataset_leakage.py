"""Integration tests against real Postgres proving `DatasetBuilder`'s
leakage-prevention claim structurally: the feature vector for a sample
never depends on what happens in its label window, and a label-window
correction that only becomes available after `data_as_of` never
changes a dataset already built at that cutoff (mirroring the same
future-correction-leakage regression proven for the Scanner pipeline
and Market Regime provider).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.repositories.market_data import InstrumentRepository, MarketBarRepository
from app.models.dataset import DatasetBuilder
from app.models.labels import LabelDefinition

_LABEL_DEFINITION = LabelDefinition(
    horizon_days=5, return_threshold=Decimal("0"), version="fwd_return_5d_v1"
)
_AS_OF_DAY = 20


def _insert_shared_history(bars: MarketBarRepository, instrument_id: int) -> None:
    rows = []
    for i in range(_AS_OF_DAY + 1):
        t = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)
        rows.append(
            {
                "instrument_id": instrument_id, "timeframe": "1d", "event_time": t,
                "available_at": t, "ingested_at": t,
                "open_price": Decimal("1000"), "high_price": Decimal("1000"),
                "low_price": Decimal("1000"), "close_price": Decimal(str(1000 + i)),
                "volume": Decimal("1000"), "currency": "KRW", "source": "test",
            }
        )
    bars.upsert_bars(rows)


def _insert_future_window(
    bars: MarketBarRepository, instrument_id: int, *, direction: str
) -> None:
    for i in range(1, 6):
        t = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=_AS_OF_DAY + i)
        close = str(1000 + _AS_OF_DAY + (i * 20 if direction == "up" else -i * 20))
        bars.upsert_bars(
            [
                {
                    "instrument_id": instrument_id, "timeframe": "1d", "event_time": t,
                    "available_at": t, "ingested_at": t,
                    "open_price": Decimal(close), "high_price": Decimal(close),
                    "low_price": Decimal(close), "close_price": Decimal(close),
                    "volume": Decimal("1000"), "currency": "KRW", "source": "test",
                }
            ]
        )


def test_feature_vector_is_identical_regardless_of_what_the_label_window_holds(
    db_session: Session,
) -> None:
    instruments = InstrumentRepository(db_session)
    bars = MarketBarRepository(db_session)

    up_instrument = instruments.get_or_create(exchange="KRX", symbol="DSETPIT_UP", source="test")
    down_instrument = instruments.get_or_create(
        exchange="KRX", symbol="DSETPIT_DOWN", source="test"
    )

    _insert_shared_history(bars, up_instrument.id)
    _insert_shared_history(bars, down_instrument.id)
    _insert_future_window(bars, up_instrument.id, direction="up")
    _insert_future_window(bars, down_instrument.id, direction="down")

    builder = DatasetBuilder(
        db_session, timeframe="1d", feature_lookback_days=30,
        label_definition=_LABEL_DEFINITION, label_lookback_days=10,
    )
    as_of = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=_AS_OF_DAY)
    data_as_of = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=_AS_OF_DAY + 10)

    result_up = builder.build(
        instrument_id=up_instrument.id, symbol="DSETPIT_UP",
        as_of_dates=[as_of], data_as_of=data_as_of,
    )
    result_down = builder.build(
        instrument_id=down_instrument.id, symbol="DSETPIT_DOWN",
        as_of_dates=[as_of], data_as_of=data_as_of,
    )

    assert len(result_up.samples) == 1
    assert len(result_down.samples) == 1

    # Same feature-window history -> identical features, regardless of
    # the wildly different label-window futures.
    assert result_up.samples[0].features.values == result_down.samples[0].features.values

    # But the labels genuinely differ, reflecting those futures.
    assert result_up.samples[0].label == 1
    assert result_down.samples[0].label == 0


def test_label_is_skipped_when_future_bars_are_not_yet_available(db_session: Session) -> None:
    instruments = InstrumentRepository(db_session)
    bars = MarketBarRepository(db_session)
    instrument = instruments.get_or_create(exchange="KRX", symbol="DSETPIT_NOFUTURE", source="test")

    _insert_shared_history(bars, instrument.id)
    # No future window inserted at all.

    builder = DatasetBuilder(
        db_session, timeframe="1d", feature_lookback_days=30,
        label_definition=_LABEL_DEFINITION, label_lookback_days=10,
    )
    as_of = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=_AS_OF_DAY)
    data_as_of = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=_AS_OF_DAY + 10)

    result = builder.build(
        instrument_id=instrument.id, symbol="DSETPIT_NOFUTURE",
        as_of_dates=[as_of], data_as_of=data_as_of,
    )
    assert result.samples == []
    assert len(result.skipped) == 1
    assert "label" in result.skipped[0].reason


def test_future_correction_leakage_regression__label_before_correction_uses_original_value(
    db_session: Session,
) -> None:
    instruments = InstrumentRepository(db_session)
    bars = MarketBarRepository(db_session)
    instrument = instruments.get_or_create(exchange="KRX", symbol="DSETPIT_CORR", source="test")
    _insert_shared_history(bars, instrument.id)

    # Filler bars for the label window's first 4 days (index 1..4) -
    # only the 5th (the horizon day itself) gets a revision history.
    for i in range(1, 5):
        t = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=_AS_OF_DAY + i)
        bars.upsert_bars(
            [
                {
                    "instrument_id": instrument.id, "timeframe": "1d", "event_time": t,
                    "available_at": t, "ingested_at": t,
                    "open_price": Decimal("1010"), "high_price": Decimal("1010"),
                    "low_price": Decimal("1010"), "close_price": Decimal("1010"),
                    "volume": Decimal("1000"), "currency": "KRW", "source": "test",
                }
            ]
        )

    label_event_time = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=_AS_OF_DAY + 5)
    original_available_at = label_event_time
    corrected_available_at = label_event_time + timedelta(days=5)

    def row(available_at: datetime, close: str) -> dict[str, object]:
        return {
            "instrument_id": instrument.id, "timeframe": "1d", "event_time": label_event_time,
            "available_at": available_at, "ingested_at": available_at,
            "open_price": Decimal(close), "high_price": Decimal(close),
            "low_price": Decimal(close), "close_price": Decimal(close),
            "volume": Decimal("1000"), "currency": "KRW", "source": "test",
        }

    # Original observation (flat), later corrected (sharp rally) - two
    # distinct available_at values, same logical (instrument, day) key.
    bars.upsert_bars([row(original_available_at, str(1000 + _AS_OF_DAY))])
    bars.upsert_bars([row(corrected_available_at, str(1000 + _AS_OF_DAY + 500))])

    builder = DatasetBuilder(
        db_session, timeframe="1d", feature_lookback_days=30,
        label_definition=_LABEL_DEFINITION, label_lookback_days=10,
    )
    as_of = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=_AS_OF_DAY)

    data_as_of_before = original_available_at + timedelta(days=1)
    result_before = builder.build(
        instrument_id=instrument.id, symbol="DSETPIT_CORR",
        as_of_dates=[as_of], data_as_of=data_as_of_before,
    )
    assert len(result_before.samples) == 1
    forward_return_before = result_before.samples[0].forward_return

    data_as_of_after = corrected_available_at + timedelta(days=1)
    result_after = builder.build(
        instrument_id=instrument.id, symbol="DSETPIT_CORR",
        as_of_dates=[as_of], data_as_of=data_as_of_after,
    )
    assert len(result_after.samples) == 1
    forward_return_after = result_after.samples[0].forward_return

    assert forward_return_before != forward_return_after
