"""Baseline quant model: L2-regularized logistic regression with
probability calibration - deliberately the simplest model that
produces a genuinely calibrated probability, per the phase's "baseline
first" requirement (see ADR 0011).

Calibration uses `sklearn.calibration.CalibratedClassifierCV` with a
`TimeSeriesSplit` internal CV (never a shuffled K-fold) - the "train/
validation must preserve chronological order" requirement holds both
at the outer split (`app.models.training`) and inside calibration
fitting itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit

from app.models.base import SignalModel


@dataclass(frozen=True)
class QuantModelConfig:
    regularization_c: float
    calibration_method: Literal["sigmoid", "isotonic"]
    calibration_splits: int
    random_state: int


class BaselineQuantModel(SignalModel):
    """Fills in Phase 00's `app.models.base.SignalModel` interface -
    `predict` is the Phase 00-compatible entry point and simply
    delegates to `predict_proba`."""

    def __init__(self, config: QuantModelConfig) -> None:
        self._config = config
        self._estimator: CalibratedClassifierCV | None = None

    def predict(self, features: np.ndarray) -> np.ndarray:
        return self.predict_proba(features)

    def fit(self, features: np.ndarray, labels: np.ndarray) -> None:
        base = LogisticRegression(
            C=self._config.regularization_c,
            max_iter=1000,
            random_state=self._config.random_state,
        )
        cv = TimeSeriesSplit(n_splits=self._config.calibration_splits)
        self._estimator = CalibratedClassifierCV(
            base, method=self._config.calibration_method, cv=cv
        )
        self._estimator.fit(features, labels)

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        if self._estimator is None:
            raise RuntimeError("BaselineQuantModel.fit must be called before predict_proba")
        return self._estimator.predict_proba(features)[:, 1]

    @property
    def fitted_estimator(self) -> CalibratedClassifierCV:
        if self._estimator is None:
            raise RuntimeError("BaselineQuantModel.fit must be called first")
        return self._estimator

    @classmethod
    def from_fitted_estimator(
        cls, estimator: CalibratedClassifierCV, config: QuantModelConfig
    ) -> BaselineQuantModel:
        """Wraps an already-fitted estimator (e.g. loaded from a saved
        artifact via `app.models.artifact.load_artifact`) - never
        refits."""
        instance = cls(config)
        instance._estimator = estimator
        return instance
