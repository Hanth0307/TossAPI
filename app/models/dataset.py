"""Leakage-safe dataset construction: for each `(instrument, as_of)`
sample, features and label are fetched from two structurally separate
`MarketBarRow` lists - the feature window (`event_time <= as_of`, via
`MarketBarRepository.get_bars_as_of(..., end=as_of, as_of=as_of)`) and
the label window (`event_time >= as_of`, fetched separately with
`as_of=data_as_of`, a later cutoff supplied explicitly by the caller
to make clear this is training-set construction, not live inference -
see `app.models.features`/`app.models.labels`). A label is never
computed from the feature window and a feature is never computed from
the label window; there is no code path that could pass one list to
both.

`data_as_of` deliberately gates the *label* fetch through the same
`as_of`-gated repository method the feature fetch uses - so a
training set built at `data_as_of=T` can never include a market-bar
correction that only became known after `T`, exactly the guarantee
`tests/db/test_point_in_time_correction.py` proves at the repository
layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.repositories.market_data import MarketBarRepository
from app.models.features import FeatureVector, compute_features
from app.models.labels import LabelDefinition, compute_forward_return_label


@dataclass(frozen=True)
class DatasetSample:
    instrument_id: int
    symbol: str
    as_of: datetime
    features: FeatureVector
    label: int
    forward_return: Decimal


@dataclass(frozen=True)
class SkippedSample:
    instrument_id: int
    as_of: datetime
    reason: str


@dataclass(frozen=True)
class DatasetBuildResult:
    samples: list[DatasetSample] = field(default_factory=list)
    skipped: list[SkippedSample] = field(default_factory=list)


class DatasetBuilder:
    def __init__(
        self,
        session: Session,
        *,
        timeframe: str,
        feature_lookback_days: int,
        label_definition: LabelDefinition,
        label_lookback_days: int,
    ) -> None:
        self._bars = MarketBarRepository(session)
        self._timeframe = timeframe
        self._feature_lookback_days = feature_lookback_days
        self._label_definition = label_definition
        self._label_lookback_days = label_lookback_days

    def build(
        self,
        *,
        instrument_id: int,
        symbol: str,
        as_of_dates: Sequence[datetime],
        data_as_of: datetime,
    ) -> DatasetBuildResult:
        samples: list[DatasetSample] = []
        skipped: list[SkippedSample] = []

        for as_of in as_of_dates:
            feature_bars = self._bars.get_bars_as_of(
                instrument_id=instrument_id,
                timeframe=self._timeframe,
                start=as_of - timedelta(days=self._feature_lookback_days),
                end=as_of,
                as_of=as_of,
            )
            feature_result = compute_features(feature_bars)
            if feature_result.vector is None:
                skipped.append(
                    SkippedSample(instrument_id, as_of, f"features: {feature_result.reason}")
                )
                continue

            label_bars = self._bars.get_bars_as_of(
                instrument_id=instrument_id,
                timeframe=self._timeframe,
                start=as_of,
                end=as_of + timedelta(days=self._label_lookback_days),
                as_of=data_as_of,
            )
            label_result = compute_forward_return_label(
                label_bars, definition=self._label_definition
            )
            if label_result.label is None or label_result.forward_return is None:
                skipped.append(
                    SkippedSample(instrument_id, as_of, f"label: {label_result.reason}")
                )
                continue

            samples.append(
                DatasetSample(
                    instrument_id=instrument_id,
                    symbol=symbol,
                    as_of=as_of,
                    features=feature_result.vector,
                    label=label_result.label,
                    forward_return=label_result.forward_return,
                )
            )

        return DatasetBuildResult(samples=samples, skipped=skipped)
