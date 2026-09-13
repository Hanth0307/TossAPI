"""Artifact save/load round trip (local filesystem, via `tmp_path`)
and `persist_training_run` integration against real Postgres -
proving a training run's metadata is recorded distinguishably per
`model_version`, the same guarantee Phase 04 proved for
`strategy_version` in `tests/scanners/test_pipeline_integration.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.schema import model_runs
from app.models.artifact import load_artifact, persist_training_run, save_artifact
from app.models.dataset import DatasetSample
from app.models.evaluation import compute_classification_metrics
from app.models.features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, FeatureVector
from app.models.labels import LabelDefinition
from app.models.model import BaselineQuantModel, QuantModelConfig
from app.models.training import TrainValidationSplit, samples_to_arrays, train_baseline_model

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_LABEL_DEFINITION = LabelDefinition(
    horizon_days=5, return_threshold=Decimal("0"), version="fwd_return_5d_v1"
)


def _synthetic_samples(count: int, *, seed: int) -> list[DatasetSample]:
    rng = np.random.default_rng(seed)
    samples = []
    for i in range(count):
        x = rng.normal(size=len(FEATURE_NAMES))
        probability = 1.0 / (1.0 + np.exp(-(2.0 * x[0])))
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


def _train(
    seed: int,
) -> tuple[BaselineQuantModel, TrainValidationSplit, np.ndarray, np.ndarray, QuantModelConfig]:
    config = QuantModelConfig(
        regularization_c=1.0, calibration_method="sigmoid", calibration_splits=3, random_state=seed
    )
    samples = _synthetic_samples(200, seed=seed)
    model, split = train_baseline_model(samples, config=config, validation_fraction=0.2)
    val_features, val_labels = samples_to_arrays(split.validation_samples)
    return model, split, val_features, val_labels, config


def test_artifact_round_trips_identical_predictions(tmp_path: Path) -> None:
    model, _split, val_features, _val_labels, config = _train(seed=1)

    path = save_artifact(model, artifact_dir=tmp_path, run_id=1)
    assert path.exists()

    reloaded = load_artifact(path, config=config)
    original_prob = model.predict_proba(val_features)
    reloaded_prob = reloaded.predict_proba(val_features)
    assert np.allclose(original_prob, reloaded_prob)


def test_persist_training_run_records_distinguishable_rows_per_model_version(
    db_session: Session, tmp_path: Path
) -> None:
    model_v1, split_v1, val_features_v1, val_labels_v1, config_v1 = _train(seed=2)
    model_v2, split_v2, val_features_v2, val_labels_v2, config_v2 = _train(seed=3)

    metrics_v1 = compute_classification_metrics(
        val_labels_v1, model_v1.predict_proba(val_features_v1), decision_threshold=0.5
    )
    metrics_v2 = compute_classification_metrics(
        val_labels_v2, model_v2.predict_proba(val_features_v2), decision_threshold=0.5
    )

    path_v1 = save_artifact(model_v1, artifact_dir=tmp_path, run_id=1001)
    path_v2 = save_artifact(model_v2, artifact_dir=tmp_path, run_id=1002)

    run_id_v1 = persist_training_run(
        db_session, model_name="quant_baseline", model_version="logreg_v1",
        feature_schema_version=FEATURE_SCHEMA_VERSION, feature_names=list(FEATURE_NAMES),
        label_definition=_LABEL_DEFINITION, config=config_v1,
        train_sample_count=len(split_v1.train_samples),
        validation_sample_count=len(split_v1.validation_samples),
        split_as_of=split_v1.split_as_of, validation_metrics=metrics_v1,
        metrics_by_period=[], metrics_by_regime=[], artifact_path=path_v1,
    )
    run_id_v2 = persist_training_run(
        db_session, model_name="quant_baseline", model_version="logreg_v2",
        feature_schema_version=FEATURE_SCHEMA_VERSION, feature_names=list(FEATURE_NAMES),
        label_definition=_LABEL_DEFINITION, config=config_v2,
        train_sample_count=len(split_v2.train_samples),
        validation_sample_count=len(split_v2.validation_samples),
        split_as_of=split_v2.split_as_of, validation_metrics=metrics_v2,
        metrics_by_period=[], metrics_by_regime=[], artifact_path=path_v2,
    )

    assert run_id_v1 != run_id_v2

    rows = (
        db_session.execute(
            select(model_runs).where(model_runs.c.id.in_([run_id_v1, run_id_v2]))
        )
        .mappings()
        .all()
    )
    versions = {row["model_version"] for row in rows}
    assert versions == {"logreg_v1", "logreg_v2"}
    for row in rows:
        assert row["status"] == "completed"
        assert row["params"]["feature_schema_version"] == FEATURE_SCHEMA_VERSION
