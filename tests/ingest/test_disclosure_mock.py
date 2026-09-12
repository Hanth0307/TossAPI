from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db.repositories.disclosure import DisclosureRepository
from app.db.schema import disclosure_events
from app.ingest.disclosure import DisclosureFiling, DisclosureIngestor, MockDisclosureCollector

NOW = datetime(2026, 3, 25, 9, 0, tzinfo=UTC)


def test_mock_collector_only_returns_filings_since_the_given_time() -> None:
    collector = MockDisclosureCollector(
        [
            DisclosureFiling(
                source="dart_mock",
                external_id="f1",
                event_time=NOW - timedelta(days=2),
                title="old",
            ),
            DisclosureFiling(
                source="dart_mock",
                external_id="f2",
                event_time=NOW - timedelta(hours=1),
                title="new",
            ),
        ]
    )
    result = collector.fetch_latest(since=NOW - timedelta(days=1))
    assert [f.external_id for f in result] == ["f2"]


def test_disclosure_ingestor_writes_through_repository_idempotently(
    migrated_schema, db_session
) -> None:
    collector = MockDisclosureCollector(
        [DisclosureFiling(source="dart_mock", external_id="f1", event_time=NOW, title="filing one")]
    )
    ingestor = DisclosureIngestor(collector, DisclosureRepository(db_session), clock=lambda: NOW)

    first = ingestor.run(since=NOW - timedelta(days=1))
    second = ingestor.run(since=NOW - timedelta(days=1))

    assert first.attempted == 1
    assert second.attempted == 1

    count = db_session.execute(select(func.count()).select_from(disclosure_events)).scalar_one()
    assert count == 1
