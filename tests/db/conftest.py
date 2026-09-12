"""Shared fixtures for `tests/db` and `tests/ingest` - a real local
PostgreSQL, not a mock: migration DDL, `ON CONFLICT` upsert semantics,
and `DISTINCT ON` point-in-time queries are all genuinely
Postgres-specific and meaningless to fake. Tests here skip gracefully
(instead of failing the suite) if no test database is reachable, so
`make test` still passes in an environment without one - see
docs/architecture/0008-data-platform.md.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/toss_quant_test"
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture(scope="session")
def database_url() -> str:
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def _require_postgres(database_url: str) -> None:
    try:
        engine = sqlalchemy.create_engine(database_url)
        with engine.connect():
            pass
        engine.dispose()
    except Exception as exc:  # noqa: BLE001 - any connection failure means "skip"
        pytest.skip(f"PostgreSQL not reachable at {database_url!r} ({exc}) - set TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def migrated_schema(_require_postgres: None, database_url: str) -> Iterator[None]:
    """Runs the real Alembic migrations (downgrade to base, then
    upgrade to head) once per test session, so every test starts from
    the exact schema `alembic upgrade head` produces - not a
    hand-maintained fixture schema that could drift from it.
    """
    cfg = _alembic_config(database_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest.fixture(scope="session")
def db_engine(migrated_schema: None, database_url: str) -> Iterator[Engine]:
    engine = sqlalchemy.create_engine(database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """One test = one transaction, rolled back at teardown - full
    isolation between tests without re-running migrations or
    truncating tables each time. Test/application code must not call
    `session.commit()` (nothing in `app.db.repositories` does) or it
    would end this outer transaction early.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
