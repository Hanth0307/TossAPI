"""Shared "get existing row by natural key, else insert" helper.

Used by every repository backing a table whose idempotency is a
lookup key rather than the bulk `ON CONFLICT DO UPDATE` pattern in
`app.db.upsert` (model_runs/backtest_runs by `idempotency_key`,
paper_orders by `client_order_id`, broker_orders by
`(broker_order_id, source)`, system_events by `dedup_key`). This is
what makes "resume after a restart" safe: calling this twice with the
same lookup key returns the same row both times instead of creating a
duplicate - see docs/architecture/0008-data-platform.md and
tests/db/test_idempotency.py.

Race-safe: if two callers race to insert the same key, the loser's
`IntegrityError` is caught (inside a `SAVEPOINT` so the outer
transaction is unaffected) and it re-reads the winner's row instead of
raising.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Table, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def get_or_insert(
    session: Session,
    table: Table,
    *,
    lookup: Mapping[str, Any],
    values: Mapping[str, Any],
    id_column: str = "id",
) -> tuple[Any, bool]:
    """Returns `(id, created)`. `created` is `False` if a row matching
    `lookup` already existed - `values` was not applied in that case.
    """
    conditions = [table.c[key] == value for key, value in lookup.items()]

    existing = session.execute(select(table.c[id_column]).where(*conditions)).scalar_one_or_none()
    if existing is not None:
        return existing, False

    try:
        with session.begin_nested():
            new_id = session.execute(
                insert(table).values(**values).returning(table.c[id_column])
            ).scalar_one()
        return new_id, True
    except IntegrityError:
        existing = session.execute(
            select(table.c[id_column]).where(*conditions)
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing, False
