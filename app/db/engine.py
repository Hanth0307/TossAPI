"""SQLAlchemy engine/session construction from `Settings`.

No connection string is ever hardcoded - `Settings.database_url` comes
from `.env` (see ADR 0002), and this module only knows how to turn it
into an `Engine`/session factory.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.exceptions import ConfigError


def build_engine(settings: Settings, *, echo: bool = False) -> Engine:
    if not settings.database_url:
        raise ConfigError(
            "database_url is not configured - set DATABASE_URL in .env (see .env.example)"
        )
    return create_engine(settings.database_url, echo=echo, future=True)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commits on success, rolls back and re-raises on any exception."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
