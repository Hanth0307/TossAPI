"""Migration up/down round trip against a real PostgreSQL database.

Runs its own downgrade/upgrade cycles independently of the shared
`migrated_schema` fixture (which only runs the cycle once per
session) - this is the test that actually proves `alembic downgrade
base` and `alembic upgrade head` both work, repeatedly, from either
direction.
"""

from __future__ import annotations

import sqlalchemy
from sqlalchemy import inspect

from alembic import command
from app.db.schema import metadata
from tests.db.conftest import _alembic_config

EXPECTED_TABLES = set(metadata.tables) | {"alembic_version"}


def _table_names(database_url: str) -> set[str]:
    engine = sqlalchemy.create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_head_creates_every_table(migrated_schema: None, database_url: str) -> None:
    assert _table_names(database_url) == EXPECTED_TABLES


def test_downgrade_base_drops_every_table_except_alembic_version(
    migrated_schema: None, database_url: str
) -> None:
    cfg = _alembic_config(database_url)
    command.downgrade(cfg, "base")
    try:
        assert _table_names(database_url) == {"alembic_version"}
    finally:
        command.upgrade(cfg, "head")  # restore for any test after this one in the session


def test_upgrade_downgrade_upgrade_round_trip_is_stable(
    migrated_schema: None, database_url: str
) -> None:
    cfg = _alembic_config(database_url)

    command.downgrade(cfg, "base")
    assert _table_names(database_url) == {"alembic_version"}

    command.upgrade(cfg, "head")
    assert _table_names(database_url) == EXPECTED_TABLES

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    assert _table_names(database_url) == EXPECTED_TABLES
