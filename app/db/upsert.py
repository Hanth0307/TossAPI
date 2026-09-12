"""Generic idempotent upsert for observed-event tables.

See docs/architecture/0008-data-platform.md. Every observed-event
table (market_bars, trade_ticks, orderbook_snapshots, news_events,
disclosure_events, signals, positions, account_snapshots) has a
natural-key `UniqueConstraint` identifying "the same real-world
event". Re-ingesting that same event is idempotent by design:

    INSERT ... ON CONFLICT (<natural key>) DO UPDATE SET <value
    columns>, ingested_at = EXCLUDED.ingested_at

`available_at` is deliberately never in the UPDATE SET clause: it
records when the row was *first* seen, and must be preserved across a
later re-ingestion/correction so that a point-in-time query
(`available_at <= as_of`, see `app.db.repositories`) keeps returning a
stable answer for a given `as_of` even if the underlying value is
later corrected. This is a documented simplification, not full
bi-temporal versioning - see the "point-in-time and corrections" note
in ADR 0008 and ADR 0009 (corporate actions) for the known limitation
and how a future phase can extend this.

Pass `on_conflict="nothing"` for tables with no meaningful "update"
(e.g. `trade_ticks`, where Toss's confirmed schema has no trade id, so
an exact-tuple conflict is treated as the same observation, not a
correction to apply).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session


def upsert_event_rows(
    session: Session,
    table: Table,
    rows: Sequence[Mapping[str, Any]],
    *,
    natural_key_columns: Sequence[str],
    update_columns: Sequence[str],
    on_conflict: Literal["update", "nothing"] = "update",
) -> int:
    """Idempotently inserts `rows` into `table`. Returns rows affected."""
    if not rows:
        return 0

    stmt = pg_insert(table).values(list(rows))

    if on_conflict == "nothing":
        stmt = stmt.on_conflict_do_nothing(index_elements=list(natural_key_columns))
    else:
        set_ = {column: getattr(stmt.excluded, column) for column in update_columns}
        set_["ingested_at"] = stmt.excluded.ingested_at
        stmt = stmt.on_conflict_do_update(index_elements=list(natural_key_columns), set_=set_)

    result = cast(CursorResult, session.execute(stmt))
    return result.rowcount or 0
