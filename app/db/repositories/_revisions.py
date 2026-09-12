"""Point-in-time read for tables using the append-only revision
pattern (`app.db.upsert.append_revision_rows`): market_bars,
news_events, disclosure_events.

Picks, per logical event, the revision with the greatest
`available_at <= as_of` - a `SELECT DISTINCT ON` ordered by
`available_at DESC, revision DESC` within each logical-key group,
wrapped in a subquery so the final result set can still be sorted
chronologically by `event_time` for the caller. This is what makes
the anti-lookahead guarantee hold even after a correction: a query
with an `as_of` before the correction's `available_at` never sees it,
because that revision row is excluded by the `available_at <= as_of`
filter entirely, not merely out-ranked - see ADR 0009 and
tests/db/test_point_in_time_correction.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, RowMapping, Table, select
from sqlalchemy.orm import Session


def select_latest_revision_as_of(
    session: Session,
    table: Table,
    *,
    logical_key_columns: Sequence[str],
    filters: Sequence[ColumnElement[bool]],
    as_of: datetime,
) -> Sequence[RowMapping]:
    distinct_columns = [table.c[name] for name in logical_key_columns]
    inner = (
        select(table)
        .where(*filters, table.c.available_at <= as_of)
        .distinct(*distinct_columns)
        .order_by(*distinct_columns, table.c.available_at.desc(), table.c.revision.desc())
        .subquery()
    )
    stmt = select(inner).order_by(inner.c.event_time)
    return session.execute(stmt).mappings().all()
