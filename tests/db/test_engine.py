from __future__ import annotations

import pytest
from pydantic import SecretStr
from sqlalchemy import delete

from app.core.config import Settings
from app.core.exceptions import ConfigError
from app.db.engine import build_engine, build_session_factory, session_scope
from app.db.repositories.system_events import SystemEventRepository
from app.db.schema import system_events


def test_build_engine_requires_database_url() -> None:
    settings = Settings(_env_file=None, database_url=None, toss_client_id=SecretStr("x"))
    with pytest.raises(ConfigError):
        build_engine(settings)


def test_session_scope_commits_on_success(migrated_schema, database_url: str) -> None:
    settings = Settings(_env_file=None, database_url=database_url)
    engine = build_engine(settings)
    factory = build_session_factory(engine)

    try:
        with session_scope(factory) as session:
            SystemEventRepository(session).log_event(
                event_type="engine_test_commit", source="test", severity="INFO", message="committed"
            )

        with session_scope(factory) as session:
            events = SystemEventRepository(session).list_recent(event_type="engine_test_commit")
            assert any(e.message == "committed" for e in events)
    finally:
        with session_scope(factory) as session:
            session.execute(
                delete(system_events).where(system_events.c.event_type == "engine_test_commit")
            )
        engine.dispose()


def test_session_scope_rolls_back_on_exception(migrated_schema, database_url: str) -> None:
    settings = Settings(_env_file=None, database_url=database_url)
    engine = build_engine(settings)
    factory = build_session_factory(engine)

    try:
        with pytest.raises(RuntimeError):
            with session_scope(factory) as session:
                SystemEventRepository(session).log_event(
                    event_type="engine_test_rollback", source="test", severity="INFO", message="x"
                )
                raise RuntimeError("boom")

        with session_scope(factory) as session:
            events = SystemEventRepository(session).list_recent(event_type="engine_test_rollback")
            assert events == []
    finally:
        engine.dispose()
