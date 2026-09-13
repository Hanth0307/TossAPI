"""`RegimeProvider`: the only place in `app.regime` that touches
`app.db` - fetches benchmark bars through `MarketBarRepository.
get_bars_as_of` (`as_of`-gated) and hands them to the pure
`RegimeClassifier`. A regime assessment is therefore exactly as
point-in-time-safe as the repository read underneath it - the same
guarantee `app.scanners.pipeline` relies on for the same reason.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.db.repositories.market_data import MarketBarRepository
from app.regime.classifier import RegimeAssessment, RegimeClassifier, RegimeInput


class RegimeProvider:
    def __init__(
        self,
        session: Session,
        *,
        classifier: RegimeClassifier,
        benchmark_instrument_id: int,
        timeframe: str,
        lookback_days: int,
    ) -> None:
        self._bars = MarketBarRepository(session)
        self._classifier = classifier
        self._benchmark_instrument_id = benchmark_instrument_id
        self._timeframe = timeframe
        self._lookback_days = lookback_days

    def get_regime_as_of(
        self,
        *,
        as_of: datetime,
        advancing_count: int | None = None,
        declining_count: int | None = None,
    ) -> RegimeAssessment:
        bars = self._bars.get_bars_as_of(
            instrument_id=self._benchmark_instrument_id,
            timeframe=self._timeframe,
            start=as_of - timedelta(days=self._lookback_days),
            end=as_of,
            as_of=as_of,
        )
        data = RegimeInput(
            bars=bars, advancing_count=advancing_count, declining_count=declining_count
        )
        return self._classifier.classify(data, as_of=as_of)
