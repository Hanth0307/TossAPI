"""Model/strategy signals - idempotent on (model_run_id, instrument_id, event_time)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.schema import signals
from app.db.upsert import upsert_event_rows


@dataclass(frozen=True)
class SignalRow:
    model_run_id: int
    instrument_id: int
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    signal_value: Decimal | None
    signal_label: str | None
    payload: dict[str, Any] | None
    source: str


class SignalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_signals(self, rows: Sequence[Mapping[str, Any]]) -> int:
        return upsert_event_rows(
            self._session,
            signals,
            rows,
            natural_key_columns=["model_run_id", "instrument_id", "event_time"],
            update_columns=["signal_value", "signal_label", "payload"],
        )

    def get_signals_as_of(
        self,
        *,
        instrument_id: int,
        start: datetime,
        end: datetime,
        as_of: datetime,
        model_run_id: int | None = None,
    ) -> list[SignalRow]:
        stmt = select(signals).where(
            signals.c.instrument_id == instrument_id,
            signals.c.event_time >= start,
            signals.c.event_time <= end,
            signals.c.available_at <= as_of,
        )
        if model_run_id is not None:
            stmt = stmt.where(signals.c.model_run_id == model_run_id)
        stmt = stmt.order_by(signals.c.event_time)

        rows = self._session.execute(stmt).mappings().all()
        return [SignalRow(**{f: row[f] for f in SignalRow.__dataclass_fields__}) for row in rows]
