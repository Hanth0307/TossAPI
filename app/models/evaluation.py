"""Evaluation: AUC is deliberately not the only metric reported. A
Signal Engine consumer thresholds this probability and compares it
across time and market regime, where class balance shifts - AUC alone
hides exactly the failure modes (miscalibration, a degenerate
precision/recall at the operating threshold, one regime dominating the
average) that matter for that use. See ADR 0011.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.models.dataset import DatasetSample


@dataclass(frozen=True)
class ClassificationMetrics:
    auc: float | None
    pr_auc: float | None
    precision: float | None
    recall: float | None
    brier_score: float
    expected_calibration_error: float
    positive_rate: float
    sample_count: int


def expected_calibration_error(
    y_true: np.ndarray, y_prob: np.ndarray, *, n_bins: int = 10
) -> float:
    """Mean, sample-weighted gap between each probability bin's average
    predicted probability and its actual positive rate - a scalar
    summary of a reliability curve."""
    if len(y_true) == 0:
        return float("nan")

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = len(y_true)
    error = 0.0
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            mask = (y_prob >= lo) & (y_prob <= hi)
        else:
            mask = (y_prob >= lo) & (y_prob < hi)
        if not mask.any():
            continue
        bin_confidence = float(y_prob[mask].mean())
        bin_accuracy = float(y_true[mask].mean())
        error += (mask.sum() / total) * abs(bin_confidence - bin_accuracy)
    return float(error)


def compute_classification_metrics(
    y_true: np.ndarray, y_prob: np.ndarray, *, decision_threshold: float
) -> ClassificationMetrics:
    sample_count = int(len(y_true))
    if sample_count == 0:
        return ClassificationMetrics(
            auc=None, pr_auc=None, precision=None, recall=None,
            brier_score=float("nan"), expected_calibration_error=float("nan"),
            positive_rate=float("nan"), sample_count=0,
        )

    positive_rate = float(np.mean(y_true))
    y_pred = (y_prob >= decision_threshold).astype(int)

    auc = None
    pr_auc = None
    if len(set(y_true.tolist())) > 1:
        auc = float(roc_auc_score(y_true, y_prob))
        pr_auc = float(average_precision_score(y_true, y_prob))

    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    brier = float(brier_score_loss(y_true, y_prob))
    ece = expected_calibration_error(y_true, y_prob)

    return ClassificationMetrics(
        auc=auc,
        pr_auc=pr_auc,
        precision=precision,
        recall=recall,
        brier_score=brier,
        expected_calibration_error=ece,
        positive_rate=positive_rate,
        sample_count=sample_count,
    )


@dataclass(frozen=True)
class GroupedMetrics:
    group_key: str
    metrics: ClassificationMetrics


def compute_metrics_by_group(
    samples: Sequence[DatasetSample],
    y_true: np.ndarray,
    y_prob: np.ndarray,
    *,
    group_key_fn: Callable[[DatasetSample], str],
    decision_threshold: float,
) -> list[GroupedMetrics]:
    """Generic grouped breakdown - used for both per-period (e.g. by
    month) and per-regime (e.g. by `RegimeAssessment.trend`) reporting,
    with the grouping key supplied by the caller so this module stays
    independent of `app.regime`."""
    groups: dict[str, list[int]] = {}
    for index, sample in enumerate(samples):
        groups.setdefault(group_key_fn(sample), []).append(index)

    result = []
    for key in sorted(groups):
        indices = np.array(groups[key])
        metrics = compute_classification_metrics(
            y_true[indices], y_prob[indices], decision_threshold=decision_threshold
        )
        result.append(GroupedMetrics(group_key=key, metrics=metrics))
    return result
