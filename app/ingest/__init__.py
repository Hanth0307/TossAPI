"""Ingestion orchestration: pulls from external sources (`app.toss`,
collector interfaces here, `app.research`'s Strategy Registry) and
writes through `app.db.repositories`.

Depends on `app.core`, `app.db`, `app.toss`, `app.data`, and
`app.research` - the one place all of these meet. Nothing downstream
of `app.db`/`app.toss`/`app.research` depends on `app.ingest` (see
docs/architecture/0001-module-boundaries.md and
docs/architecture/0008-data-platform.md): a bug here can never corrupt
those packages' own invariants (Toss read-only enforcement, Strategy
Registry file format, the Data Platform's point-in-time guarantee),
because none of them import anything from `app.ingest`.

Mock-first: `app.ingest.news.MockNewsCollector` and
`app.ingest.disclosure.MockDisclosureCollector` are deterministic,
in-memory stand-ins for external APIs this project has not integrated
yet - implementing the same `Protocol` a real collector would, so
swapping one in later is additive, not a rewrite.
"""
