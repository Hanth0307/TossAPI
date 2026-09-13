"""Time-ordered train/validation split - never shuffled, per the
phase's requirement that train/validation preserve chronological
order. A random/shuffled split would let the model train on samples
that occur chronologically after ones it is validated against - a
leakage source distinct from (and in addition to) the feature/label
separation `app.models.dataset` enforces.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from app.models.dataset import DatasetSample
from app.models.model import BaselineQuantModel, QuantModelConfig


@dataclass(frozen=True)
class TrainValidationSplit:
    train_samples: list[DatasetSample]
    validation_samples: list[DatasetSample]
    split_as_of: datetime


def time_ordered_split(
    samples: Sequence[DatasetSample], *, validation_fraction: float
) -> TrainValidationSplit:
    if not 0.0 < validation_fraction < 1.0:
        raise ValueError("validation_fraction must be between 0 and 1 exclusive")
    if len(samples) < 2:
        raise ValueError("need at least 2 samples to form a train/validation split")

    ordered = sorted(samples, key=lambda s: s.as_of)
    split_index = round(len(ordered) * (1 - validation_fraction))
    split_index = min(max(split_index, 1), len(ordered) - 1)

    train = ordered[:split_index]
    validation = ordered[split_index:]
    return TrainValidationSplit(
        train_samples=train, validation_samples=validation, split_as_of=validation[0].as_of
    )


def samples_to_arrays(samples: Sequence[DatasetSample]) -> tuple[np.ndarray, np.ndarray]:
    features = np.array([sample.features.as_ordered_list() for sample in samples])
    labels = np.array([sample.label for sample in samples])
    return features, labels


def train_baseline_model(
    samples: Sequence[DatasetSample], *, config: QuantModelConfig, validation_fraction: float
) -> tuple[BaselineQuantModel, TrainValidationSplit]:
    split = time_ordered_split(samples, validation_fraction=validation_fraction)
    train_features, train_labels = samples_to_arrays(split.train_samples)
    model = BaselineQuantModel(config)
    model.fit(train_features, train_labels)
    return model, split
