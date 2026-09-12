"""Two idempotent write strategies for observed-event tables.

See docs/architecture/0008-data-platform.md and ADR 0009.

`upsert_event_rows` - for tables where a re-observation is never
expected to be a *correction* worth preserving history for (`trade_ticks`,
`orderbook_snapshots`, `signals`, `positions`, `account_snapshots`):

    INSERT ... ON CONFLICT (<natural key>) DO UPDATE SET <value
    columns>, ingested_at = EXCLUDED.ingested_at

`available_at` is never in that `SET` clause - it is preserved from
first insert. **This means a later correction's new value becomes
visible to a point-in-time query whose `as_of` predates the
correction - a real leak of not-yet-available information into a
backtest/training query.** That is fine only because these particular
tables are not expected to receive external corrections; it would be
a bug for any table that does. See `append_revision_rows` below.

`append_revision_rows` - for tables where an external source can issue
a correction with new values at a later `available_at`
(`market_bars`, `news_events`, `disclosure_events`): every correction
is INSERTed as a new row (a new `revision`), never overwrites the
prior one, and `available_at` is part of the natural key rather than
excluded from it:

    INSERT ... ON CONFLICT (<natural key>, available_at) DO UPDATE SET
    ingested_at = EXCLUDED.ingested_at   -- only for an exact resubmission

A point-in-time read (`app.db.repositories._revisions.
select_latest_revision_as_of`) then picks, per logical event, the
revision with the greatest `available_at <= as_of` - so a query for an
`as_of` before the correction's `available_at` still sees the
*original* value, and one for an `as_of` after sees the correction.
Re-submitting the exact same correction (identical `available_at`) is
still idempotent - it hits the same `ON CONFLICT` row and only
`ingested_at` changes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from sqlalchemy import Table, func, select
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


def append_revision_rows(
    session: Session,
    table: Table,
    rows: Sequence[Mapping[str, Any]],
    *,
    logical_key_columns: Sequence[str],
) -> int:
    """Appends one new revision row per event in `rows` - never
    overwrites a prior revision's values or `available_at`.

    `table` must have a `revision` integer column and a
    `UniqueConstraint(*logical_key_columns, "available_at")` (see
    `app.db.schema`). `revision` is computed here as `1 + the current
    max revision for this logical event` - rows are processed one at a
    time (not a single bulk statement) so that two corrections for the
    same event submitted in one call get distinct, correctly-ordered
    revision numbers rather than racing against the same "before this
    call" max. This assumes a single writer per logical event within a
    call, which holds for every caller in this codebase (Phase 03 has
    no concurrent ingestion pipelines yet) - see ADR 0009.

    Resubmitting a row with a logical key + `available_at` that already
    exists is idempotent: it updates only `ingested_at` on the existing
    revision, never its value columns.
    """
    if not rows:
        return 0

    affected = 0
    for row in rows:
        conditions = [table.c[column] == row[column] for column in logical_key_columns]
        next_revision = (
            select(func.coalesce(func.max(table.c.revision), 0) + 1)
            .where(*conditions)
            .scalar_subquery()
        )
        insert_stmt = pg_insert(table).values(revision=next_revision, **row)
        insert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[*logical_key_columns, "available_at"],
            set_={"ingested_at": insert_stmt.excluded.ingested_at},
        )
        result = cast(CursorResult, session.execute(insert_stmt))
        affected += result.rowcount or 0
    return affected
