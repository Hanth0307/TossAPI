"""Model/backtest run tracking - resumable via `idempotency_key`.

Calling `start_run`/`start_backtest` twice with the same
`idempotency_key` returns the same run both times (`created=False` the
second time) instead of creating a duplicate - this is what makes
"restart the pipeline and re-run the same job" safe. See
`app.db.repositories._idempotent_insert.get_or_insert` and
docs/architecture/0008-data-platform.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.db.repositories._idempotent_insert import get_or_insert
from app.db.schema import backtest_runs, model_runs


class ModelRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def start_run(
        self,
        *,
        model_name: str,
        model_version: str | None = None,
        strategy_id: str | None = None,
        strategy_version: str | None = None,
        params: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[int, bool]:
        values = {
            "model_name": model_name,
            "model_version": model_version,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "status": "running",
            "idempotency_key": idempotency_key,
            "params": params,
        }
        if idempotency_key is None:
            run_id = self._session.execute(
                model_runs.insert().values(**values).returning(model_runs.c.id)
            ).scalar_one()
            return run_id, True
        return get_or_insert(
            self._session,
            model_runs,
            lookup={"idempotency_key": idempotency_key},
            values=values,
        )

    def finish_run(
        self, run_id: int, *, status: str, metrics: Mapping[str, Any] | None = None
    ) -> None:
        self._session.execute(
            update(model_runs)
            .where(model_runs.c.id == run_id)
            .values(status=status, finished_at=func.now(), metrics=metrics)
        )


class BacktestRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def start_backtest(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        period_start: datetime,
        period_end: datetime,
        params: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[int, bool]:
        values = {
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "status": "running",
            "idempotency_key": idempotency_key,
            "period_start": period_start,
            "period_end": period_end,
            "params": params,
        }
        if idempotency_key is None:
            run_id = self._session.execute(
                backtest_runs.insert().values(**values).returning(backtest_runs.c.id)
            ).scalar_one()
            return run_id, True
        return get_or_insert(
            self._session,
            backtest_runs,
            lookup={"idempotency_key": idempotency_key},
            values=values,
        )

    def finish_backtest(
        self, run_id: int, *, status: str, metrics: Mapping[str, Any] | None = None
    ) -> None:
        self._session.execute(
            update(backtest_runs)
            .where(backtest_runs.c.id == run_id)
            .values(status=status, finished_at=func.now(), metrics=metrics)
        )
