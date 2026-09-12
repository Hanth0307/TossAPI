"""Data Platform: PostgreSQL schema, migrations, and repositories.

Depends on `app.core` only (`Settings.database_url`, exceptions). No
import edge to `app.toss`, `app.research`, `app.brokers`, `app.risk`,
or `app.execution` - this package only knows how to store and query
rows; it never fetches anything itself (`app.ingest` is the layer that
pulls from `app.toss`/`app.research`/collector interfaces and writes
through the repositories defined here).

See docs/architecture/0008-data-platform.md for the entity list, the
event_time/available_at/ingested_at convention, idempotency rules, and
the point-in-time query guarantee every historical read method in
`app.db.repositories` enforces.
"""
