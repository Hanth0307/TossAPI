"""`SignalEngine`: the only place `app.signals` touches `app.db` -
computes a Quant Model probability from `as_of`-gated bars (via
`app.models.features.compute_features` +
`app.db.repositories.market_data.MarketBarRepository`) and a Market
Regime assessment (via `app.regime.provider.RegimeProvider`, itself
`as_of`-gated), then structures them together with whatever AI Context
the caller supplies into one `SignalInput` (`app.signals.schema`).

**AI Context is supplied by the caller, not fetched here.** Which
news/disclosure items are "relevant" to an instrument at a given
`as_of` is a judgment call (symbol match, lookback window, novelty/
dedup handling) that belongs with whoever is assembling a signal run -
this engine only structures already-computed `AIContextResult`s
(typically loaded via `app.ai_context.persistence.
load_annotations_as_of`) alongside the two inputs it does compute
itself.

**No order is generated anywhere in this call chain.** `build_signal_input`
returns a `SignalInput` - evidence for a later phase, not an
instruction. See ADR 0011.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from app.ai_context.schema import AIContextResult
from app.db.repositories.market_data import MarketBarRepository
from app.models.features import compute_features
from app.models.model import BaselineQuantModel
from app.regime.provider import RegimeProvider
from app.signals.schema import QuantProbability, SignalInput, build_signal_input


class SignalEngine:
    def __init__(
        self,
        session: Session,
        *,
        regime_provider: RegimeProvider,
        quant_model: BaselineQuantModel | None,
        quant_model_name: str,
        quant_model_version: str,
        quant_feature_schema_version: str,
        quant_label_definition_version: str,
        feature_timeframe: str,
        feature_lookback_days: int,
    ) -> None:
        self._bars = MarketBarRepository(session)
        self._regime_provider = regime_provider
        self._quant_model = quant_model
        self._quant_model_name = quant_model_name
        self._quant_model_version = quant_model_version
        self._quant_feature_schema_version = quant_feature_schema_version
        self._quant_label_definition_version = quant_label_definition_version
        self._feature_timeframe = feature_timeframe
        self._feature_lookback_days = feature_lookback_days

    def _compute_quant_probability(
        self, *, instrument_id: int, as_of: datetime
    ) -> QuantProbability | None:
        if self._quant_model is None:
            return None
        bars = self._bars.get_bars_as_of(
            instrument_id=instrument_id,
            timeframe=self._feature_timeframe,
            start=as_of - timedelta(days=self._feature_lookback_days),
            end=as_of,
            as_of=as_of,
        )
        feature_result = compute_features(bars)
        if feature_result.vector is None:
            return None

        matrix = np.array([feature_result.vector.as_ordered_list()])
        probability = float(self._quant_model.predict_proba(matrix)[0])
        return QuantProbability(
            model_name=self._quant_model_name,
            model_version=self._quant_model_version,
            feature_schema_version=self._quant_feature_schema_version,
            label_definition_version=self._quant_label_definition_version,
            probability=probability,
            as_of=as_of,
        )

    def build_signal_input(
        self,
        *,
        instrument_id: int,
        symbol: str,
        as_of: datetime,
        ai_context: Sequence[AIContextResult] = (),
        advancing_count: int | None = None,
        declining_count: int | None = None,
    ) -> SignalInput:
        regime = self._regime_provider.get_regime_as_of(
            as_of=as_of, advancing_count=advancing_count, declining_count=declining_count
        )
        quant_probability = self._compute_quant_probability(
            instrument_id=instrument_id, as_of=as_of
        )
        return build_signal_input(
            instrument_id=instrument_id,
            symbol=symbol,
            as_of=as_of,
            generated_at=datetime.now(UTC),
            ai_context=list(ai_context),
            quant_probability=quant_probability,
            regime=regime,
        )
