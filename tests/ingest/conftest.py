"""`tests/ingest` needs the same real-Postgres fixtures as `tests/db` -
re-exported here since pytest only auto-discovers fixtures from
conftest.py files in a test's own directory chain, and `tests/ingest`
is a sibling of `tests/db`, not a subdirectory of it.
"""

from tests.db.conftest import (  # noqa: F401
    _require_postgres,
    database_url,
    db_engine,
    db_session,
    migrated_schema,
)
