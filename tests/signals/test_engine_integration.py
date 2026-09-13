"""Integration test against real Postgres for `SignalEngine` -
combines a quant probability (computed from `as_of`-gated bars), a
regime assessment (via `RegimeProvider`), and caller-supplied AI
Context into one `SignalInput`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
from sqlalchemy.orm import Session

from app.ai_context.schema import AIContextResult, EventKind, ExtractionStatus
from app.db.repositories.market_data import InstrumentRepository, MarketBarRepository
from app.models.features import FEATURE_NAMES
from app.models.model import BaselineQuantModel, QuantModelConfig
from app.regime.classifier import RegimeClassifier
from app.regime.provider import RegimeProvider
from app.signals.engine import SignalEngine


def _insert_bars(bars: MarketBarRepository, instrument_id: int, *, count: int = 21) -> None:
    rows = []
    for i in range(count):
        t = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)
        rows.append(
            {
                "instrument_id": instrument_id, "timeframe": "1d", "event_time": t,
                "available_at": t, "ingested_at": t,
                "open_price": Decimal("1000"), "high_price": Decimal("1010"),
                "low_price": Decimal("990"), "close_price": Decimal(str(1000 + i)),
                "volume": Decimal("1000"), "currency": "KRW", "source": "test",
            }
        )
    bars.upsert_bars(rows)


def _classifier() -> RegimeClassifier:
    return RegimeClassifier(
        trend_lookback_bars=20,
        trend_up_threshold=Decimal("0.03"),
        trend_down_threshold=Decimal("-0.03"),
        volatility_lookback_bars=20,
        high_volatility_threshold=Decimal("0.02"),
        low_volatility_threshold=Decimal("0.0001"),
        breadth_expanding_threshold=Decimal("0.6"),
        breadth_contracting_threshold=Decimal("0.4"),
    )


def _trained_model() -> BaselineQuantModel:
    rng = np.random.default_rng(0)
    features = rng.normal(size=(60, len(FEATURE_NAMES)))
    labels = (rng.random(60) < 0.5).astype(int)
    config = QuantModelConfig(
        regularization_c=1.0, calibration_method="sigmoid", calibration_splits=3, random_state=0
    )
    model = BaselineQuantModel(config)
    model.fit(features, labels)
    return model


def test_signal_engine_combines_quant_probability_regime_and_supplied_ai_context(
    db_session: Session,
) -> None:
    instruments = InstrumentRepository(db_session)
    bars = MarketBarRepository(db_session)

    target = instruments.get_or_create(exchange="KRX", symbol="SIGTEST", source="test")
    benchmark = instruments.get_or_create(exchange="KRX", symbol="SIGBENCH", source="test")
    _insert_bars(bars, target.id)
    _insert_bars(bars, benchmark.id)

    regime_provider = RegimeProvider(
        db_session, classifier=_classifier(),
        benchmark_instrument_id=benchmark.id, timeframe="1d", lookback_days=30,
    )

    engine = SignalEngine(
        db_session,
        regime_provider=regime_provider,
        quant_model=_trained_model(),
        quant_model_name="quant_baseline",
        quant_model_version="logreg_v1",
        quant_feature_schema_version="1.0.0",
        quant_label_definition_version="fwd_return_5d_v1",
        feature_timeframe="1d",
        feature_lookback_days=30,
    )

    ai_context = [
        AIContextResult(
            status=ExtractionStatus.OK, source="mock_news", external_id="n-1",
            event_kind=EventKind.NEWS, model_name="mock", model_version="0.0.0",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    as_of = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=20)

    signal = engine.build_signal_input(
        instrument_id=target.id, symbol="SIGTEST", as_of=as_of, ai_context=ai_context,
        advancing_count=600, declining_count=400,
    )

    assert signal.instrument_id == target.id
    assert signal.symbol == "SIGTEST"
    assert signal.has_ai_context is True
    assert signal.ai_context[0].external_id == "n-1"

    assert signal.has_quant_probability is True
    assert signal.quant_probability is not None
    assert 0.0 <= signal.quant_probability.probability <= 1.0
    assert signal.quant_probability.model_version == "logreg_v1"

    assert signal.has_regime is True
    assert signal.regime is not None
    assert signal.regime.breadth.value in {"expanding", "contracting", "neutral", "unknown"}


def test_signal_engine_reports_no_quant_probability_when_history_is_too_short(
    db_session: Session,
) -> None:
    instruments = InstrumentRepository(db_session)
    bars = MarketBarRepository(db_session)

    target = instruments.get_or_create(exchange="KRX", symbol="SIGTEST_SHORT", source="test")
    benchmark = instruments.get_or_create(exchange="KRX", symbol="SIGBENCH_SHORT", source="test")
    _insert_bars(bars, target.id, count=5)  # not enough history for compute_features
    _insert_bars(bars, benchmark.id, count=5)

    regime_provider = RegimeProvider(
        db_session, classifier=_classifier(),
        benchmark_instrument_id=benchmark.id, timeframe="1d", lookback_days=30,
    )
    engine = SignalEngine(
        db_session,
        regime_provider=regime_provider,
        quant_model=_trained_model(),
        quant_model_name="quant_baseline",
        quant_model_version="logreg_v1",
        quant_feature_schema_version="1.0.0",
        quant_label_definition_version="fwd_return_5d_v1",
        feature_timeframe="1d",
        feature_lookback_days=30,
    )

    as_of = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=4)
    signal = engine.build_signal_input(instrument_id=target.id, symbol="SIGTEST_SHORT", as_of=as_of)

    assert signal.has_quant_probability is False
    assert signal.quant_probability is None
