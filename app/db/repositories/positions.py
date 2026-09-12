"""Position snapshots - idempotent on (account_id, instrument_id, event_time, source).

`get_current_positions_as_of` returns the latest snapshot per
instrument with `available_at <= as_of` (Postgres `DISTINCT ON`), i.e.
"what the portfolio looked like as of that point in time" - never a
snapshot that only became available later.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.schema import positions
from app.db.upsert import upsert_event_rows


@dataclass(frozen=True)
class PositionRow:
    account_id: str
    instrument_id: int
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    quantity: Decimal
    avg_price: Decimal | None
    source: str


class PositionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_positions(self, rows: Sequence[Mapping[str, Any]]) -> int:
        return upsert_event_rows(
            self._session,
            positions,
            rows,
            natural_key_columns=["account_id", "instrument_id", "event_time", "source"],
            update_columns=["quantity", "avg_price"],
        )

    def get_current_positions_as_of(
        self, *, account_id: str, as_of: datetime
    ) -> list[PositionRow]:
        stmt = (
            select(positions)
            .where(positions.c.account_id == account_id, positions.c.available_at <= as_of)
            .distinct(positions.c.instrument_id)
            .order_by(positions.c.instrument_id, positions.c.event_time.desc())
        )
        rows = self._session.execute(stmt).mappings().all()
        return [
            PositionRow(**{f: row[f] for f in PositionRow.__dataclass_fields__}) for row in rows
        ]
