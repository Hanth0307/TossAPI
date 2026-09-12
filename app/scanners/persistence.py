"""Persists `Candidate`s from one `ScannerPipeline.scan()` call as a
`model_runs` row (keyed by `strategy_id` + `strategy_version` +
`idempotency_key`) and one `signals` row per candidate.

This is what makes "전략 버전 변경 시 결과가 구분 저장" (results are
stored separately when the strategy version changes) an actual,
checkable property of the database rather than just a design
intention: two calls with different `strategy_version` values produce
two distinct `model_runs` rows, and every `signals` row is tied to its
own `model_run_id` - see
`tests/scanners/test_pipeline_integration.py::
test_strategy_version_segregation__*`.

A `Candidate`'s full evidence (universe/event/strategy condition
results) is stored as the signal's JSON `payload` - `Decimal` values
are serialized as strings (JSON has no native decimal type) so no
precision is silently lost.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories.runs import ModelRunRepository
from app.db.repositories.signals import SignalRepository
from app.scanners.candidate import Candidate


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


def _candidate_payload(candidate: Candidate) -> dict[str, Any]:
    return {
        "universe_results": [_json_safe(asdict(r)) for r in candidate.universe_results],
        "event_detections": [_json_safe(asdict(d)) for d in candidate.event_detections],
        "strategy_result": (
            _json_safe(asdict(candidate.strategy_result))
            if candidate.strategy_result is not None
            else None
        ),
        "qualified": candidate.qualified,
    }


def persist_scan_results(
    session: Session,
    candidates: Sequence[Candidate],
    *,
    model_name: str,
    strategy_id: str,
    strategy_version: str,
    as_of: datetime,
    idempotency_key: str | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    run_repository = ModelRunRepository(session)
    signal_repository = SignalRepository(session)

    run_id, _created = run_repository.start_run(
        model_name=model_name,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        idempotency_key=idempotency_key,
    )

    now = clock()
    rows = [
        {
            "model_run_id": run_id,
            "instrument_id": candidate.instrument_id,
            "event_time": as_of,
            "available_at": now,
            "ingested_at": now,
            "signal_value": Decimal(1) if candidate.qualified else Decimal(0),
            "signal_label": "qualified" if candidate.qualified else "not_qualified",
            "payload": _candidate_payload(candidate),
            "source": model_name,
        }
        for candidate in candidates
    ]
    # `SignalRepository.upsert_signals`' own return value (a driver
    # `CursorResult.rowcount`) is unreliable for this table - psycopg
    # reports it as -1 for an INSERT that also does an implicit
    # RETURNING (SQLAlchemy 2.0 adds this automatically to fetch the
    # autoincrement `id`). We already know exactly how many rows we
    # intended to write, so report that instead of trusting rowcount.
    signal_repository.upsert_signals(rows)
    persisted = len(rows)

    run_repository.finish_run(
        run_id,
        status="completed",
        metrics={
            "candidate_count": len(candidates),
            "qualified_count": sum(1 for c in candidates if c.qualified),
        },
    )
    return persisted
