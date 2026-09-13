"""Pure (no database) tests for time-ordered splitting, calibration/
classification metrics, grouped evaluation, and permutation importance
- exercised end to end against synthetic data with a known, separable
relationship between one feature and the label.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from app.models.dataset import DatasetSample
from app.models.evaluation import (
    compute_classification_metrics,
    compute_metrics_by_group,
    expected_calibration_error,
)
from app.models.features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, FeatureVector
from app.models.importance import compute_permutation_importance
from app.models.model import QuantModelConfig
from app.models.training import samples_to_arrays, time_ordered_split, train_baseline_model

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _sample(i: int, label: int) -> DatasetSample:
    values = dict.fromkeys(FEATURE_NAMES, 0.0)
    values["return_1d"] = 1.0 if label else -1.0
    return DatasetSample(
        instrument_id=1, symbol="TEST", as_of=_BASE_TIME + timedelta(days=i),
        features=FeatureVector(schema_version=FEATURE_SCHEMA_VERSION, values=values),
        label=label, forward_return=Decimal("0.01") if label else Decimal("-0.01"),
    )


def _synthetic_samples(count: int, *, seed: int) -> list[DatasetSample]:
    rng = np.random.default_rng(seed)
    samples = []
    for i in range(count):
        x = rng.normal(size=len(FEATURE_NAMES))
        probability = 1.0 / (1.0 + np.exp(-(2.0 * x[0] + 0.3 * x[1])))
        label = int(rng.random() < probability)
        values = dict(zip(FEATURE_NAMES, x.tolist(), strict=True))
        samples.append(
            DatasetSample(
                instrument_id=1, symbol="TEST", as_of=_BASE_TIME + timedelta(days=i),
                features=FeatureVector(schema_version=FEATURE_SCHEMA_VERSION, values=values),
                label=label, forward_return=Decimal("0.01") if label else Decimal("-0.01"),
            )
        )
    return samples


def test_time_ordered_split_keeps_all_train_as_of_before_all_validation_as_of() -> None:
    samples = [_sample(i, i % 2) for i in range(20)]
    split = time_ordered_split(samples, validation_fraction=0.25)
    latest_train_as_of = max(s.as_of for s in split.train_samples)
    earliest_validation_as_of = min(s.as_of for s in split.validation_samples)
    assert latest_train_as_of < earliest_validation_as_of
    assert len(split.train_samples) + len(split.validation_samples) == len(samples)


def test_time_ordered_split_is_insensitive_to_input_order() -> None:
    """Feeding samples in shuffled order must not change the split -
    the function sorts by as_of itself, it never trusts input order."""
    ordered = [_sample(i, i % 2) for i in range(20)]
    shuffled = list(reversed(ordered))
    split_from_ordered = time_ordered_split(ordered, validation_fraction=0.25)
    split_from_shuffled = time_ordered_split(shuffled, validation_fraction=0.25)
    assert [s.as_of for s in split_from_ordered.train_samples] == [
        s.as_of for s in split_from_shuffled.train_samples
    ]


def test_time_ordered_split_rejects_invalid_fraction() -> None:
    samples = [_sample(i, i % 2) for i in range(10)]
    with pytest.raises(ValueError, match="validation_fraction"):
        time_ordered_split(samples, validation_fraction=1.0)
    with pytest.raises(ValueError, match="validation_fraction"):
        time_ordered_split(samples, validation_fraction=0.0)


def test_time_ordered_split_rejects_too_few_samples() -> None:
    with pytest.raises(ValueError, match="at least 2 samples"):
        time_ordered_split([_sample(0, 1)], validation_fraction=0.5)


def test_classification_metrics_on_perfectly_separable_predictions() -> None:
    y_true = np.array([0, 0, 0, 1, 1, 1])
    y_prob = np.array([0.05, 0.1, 0.15, 0.85, 0.9, 0.95])
    metrics = compute_classification_metrics(y_true, y_prob, decision_threshold=0.5)
    assert metrics.auc == 1.0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.sample_count == 6
    assert metrics.positive_rate == 0.5


def test_classification_metrics_with_no_samples_reports_nan_not_an_exception() -> None:
    metrics = compute_classification_metrics(np.array([]), np.array([]), decision_threshold=0.5)
    assert metrics.sample_count == 0
    assert metrics.auc is None


def test_expected_calibration_error_is_near_zero_for_well_calibrated_predictions() -> None:
    rng = np.random.default_rng(0)
    y_prob = rng.uniform(0.0, 1.0, size=5000)
    y_true = (rng.uniform(0.0, 1.0, size=5000) < y_prob).astype(int)
    ece = expected_calibration_error(y_true, y_prob, n_bins=10)
    assert ece < 0.05


def test_expected_calibration_error_is_high_for_badly_miscalibrated_predictions() -> None:
    y_true = np.array([0] * 50 + [1] * 50)
    y_prob = np.array([0.9] * 50 + [0.1] * 50)  # confidently wrong both ways
    ece = expected_calibration_error(y_true, y_prob, n_bins=10)
    assert ece > 0.7


def test_compute_metrics_by_group_splits_by_supplied_key() -> None:
    samples = [_sample(i, i % 2) for i in range(10)]
    y_true = np.array([s.label for s in samples])
    y_prob = np.array([0.9 if s.label else 0.1 for s in samples])
    grouped = compute_metrics_by_group(
        samples, y_true, y_prob,
        group_key_fn=lambda s: "even" if s.as_of.day % 2 == 0 else "odd",
        decision_threshold=0.5,
    )
    keys = {g.group_key for g in grouped}
    assert keys == {"even", "odd"}
    assert sum(g.metrics.sample_count for g in grouped) == 10


def test_train_baseline_model_produces_calibrated_probabilities_in_unit_range() -> None:
    samples = _synthetic_samples(300, seed=42)
    config = QuantModelConfig(
        regularization_c=1.0, calibration_method="sigmoid", calibration_splits=3, random_state=42
    )
    model, split = train_baseline_model(samples, config=config, validation_fraction=0.2)

    val_features, val_labels = samples_to_arrays(split.validation_samples)
    val_prob = model.predict_proba(val_features)

    assert val_prob.min() >= 0.0
    assert val_prob.max() <= 1.0

    metrics = compute_classification_metrics(val_labels, val_prob, decision_threshold=0.5)
    assert metrics.auc is not None and metrics.auc > 0.6


def test_permutation_importance_ranks_the_informative_feature_highest() -> None:
    samples = _synthetic_samples(300, seed=7)
    config = QuantModelConfig(
        regularization_c=1.0, calibration_method="sigmoid", calibration_splits=3, random_state=7
    )
    model, split = train_baseline_model(samples, config=config, validation_fraction=0.2)
    val_features, val_labels = samples_to_arrays(split.validation_samples)

    importances = compute_permutation_importance(
        model, val_features, val_labels, n_repeats=10, random_state=7
    )
    assert importances[0].feature_name == "return_1d"
