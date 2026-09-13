"""Model artifact storage: the fitted estimator is serialized with
joblib to a file, and everything needed to reproduce or audit the
training run - feature schema version/names, the label definition,
hyperparameters, the train/validation window, and the computed
evaluation metrics - is stored on the existing Phase 03 `model_runs`
table (`app.db.repositories.runs.ModelRunRepository`). No new
migration was needed for this: `model_runs.params`/`metrics` (JSONB)
already exist for exactly this purpose.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import joblib
from sqlalchemy.orm import Session

from app.db.repositories.runs import ModelRunRepository
from app.models.evaluation import ClassificationMetrics, GroupedMetrics
from app.models.labels import LabelDefinition
from app.models.model import BaselineQuantModel, QuantModelConfig


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def save_artifact(model: BaselineQuantModel, *, artifact_dir: Path, run_id: int) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{run_id}.joblib"
    joblib.dump(model.fitted_estimator, path)
    return path


def load_artifact(path: Path, *, config: QuantModelConfig) -> BaselineQuantModel:
    estimator = joblib.load(path)
    return BaselineQuantModel.from_fitted_estimator(estimator, config)


def persist_training_run(
    session: Session,
    *,
    model_name: str,
    model_version: str,
    feature_schema_version: str,
    feature_names: list[str],
    label_definition: LabelDefinition,
    config: QuantModelConfig,
    train_sample_count: int,
    validation_sample_count: int,
    split_as_of: datetime,
    validation_metrics: ClassificationMetrics,
    metrics_by_period: list[GroupedMetrics],
    metrics_by_regime: list[GroupedMetrics],
    artifact_path: Path,
    idempotency_key: str | None = None,
) -> int:
    """Starts and immediately finishes a `model_runs` row for one
    completed baseline-quant training run. Returns the `model_runs.id`
    - the same id `save_artifact` uses to name the artifact file, so
    the DB row and the file on disk are always addressed by the same
    key."""
    run_repository = ModelRunRepository(session)
    params = {
        "feature_schema_version": feature_schema_version,
        "feature_names": feature_names,
        "label_definition": asdict(label_definition),
        "config": asdict(config),
        "train_sample_count": train_sample_count,
        "validation_sample_count": validation_sample_count,
        "split_as_of": split_as_of,
        "artifact_path": str(artifact_path),
    }
    metrics = {
        "validation": asdict(validation_metrics),
        "by_period": [
            {"group_key": g.group_key, "metrics": asdict(g.metrics)} for g in metrics_by_period
        ],
        "by_regime": [
            {"group_key": g.group_key, "metrics": asdict(g.metrics)} for g in metrics_by_regime
        ],
    }

    run_id, _created = run_repository.start_run(
        model_name=model_name,
        model_version=model_version,
        params=_json_safe(params),
        idempotency_key=idempotency_key,
    )
    run_repository.finish_run(run_id, status="completed", metrics=_json_safe(metrics))
    return run_id
