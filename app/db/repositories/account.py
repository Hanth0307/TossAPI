"""Account balance snapshots - idempotent on (account_id, event_time, source).

Normalized columns (`cash_balance`, `buying_power`) are nullable:
Toss's account/balance response field names are unconfirmed per ADR
0007, so `raw_payload` is the primary content until they are.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.schema import account_snapshots
from app.db.upsert import upsert_event_rows


@dataclass(frozen=True)
class AccountSnapshotRow:
    account_id: str
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    cash_balance: Decimal | None
    buying_power: Decimal | None
    source: str


class AccountSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_snapshots(self, rows: Sequence[Mapping[str, Any]]) -> int:
        return upsert_event_rows(
            self._session,
            account_snapshots,
            rows,
            natural_key_columns=["account_id", "event_time", "source"],
            update_columns=["cash_balance", "buying_power", "raw_payload"],
        )

    def get_latest_as_of(self, *, account_id: str, as_of: datetime) -> AccountSnapshotRow | None:
        stmt = (
            select(account_snapshots)
            .where(
                account_snapshots.c.account_id == account_id,
                account_snapshots.c.available_at <= as_of,
            )
            .order_by(account_snapshots.c.event_time.desc())
            .limit(1)
        )
        row = self._session.execute(stmt).mappings().one_or_none()
        if row is None:
            return None
        return AccountSnapshotRow(**{f: row[f] for f in AccountSnapshotRow.__dataclass_fields__})
