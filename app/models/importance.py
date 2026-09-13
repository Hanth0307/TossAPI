"""Feature importance via permutation importance
(`sklearn.inspection.permutation_importance`) - provided strictly as a
**validation aid**, per the phase spec ("설명 가능성은 검증 보조로 제공한다"),
never as a training or selection input. Chosen over SHAP to avoid an
additional heavy dependency for a baseline model: permutation
importance answers the same practical question this phase needs
("which features does the model's held-out accuracy actually depend
on") without it - see ADR 0011.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.inspection import permutation_importance

from app.models.features import FEATURE_NAMES
from app.models.model import BaselineQuantModel


@dataclass(frozen=True)
class FeatureImportance:
    feature_name: str
    importance_mean: float
    importance_std: float


def compute_permutation_importance(
    model: BaselineQuantModel,
    features: np.ndarray,
    labels: np.ndarray,
    *,
    n_repeats: int,
    random_state: int,
) -> list[FeatureImportance]:
    result = permutation_importance(
        model.fitted_estimator,
        features,
        labels,
        n_repeats=n_repeats,
        random_state=random_state,
        scoring="roc_auc",
    )
    importances = [
        FeatureImportance(feature_name=name, importance_mean=float(mean), importance_std=float(std))
        for name, mean, std in zip(
            FEATURE_NAMES, result.importances_mean, result.importances_std, strict=True
        )
    ]
    return sorted(importances, key=lambda item: item.importance_mean, reverse=True)
