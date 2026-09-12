from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db.repositories.news import NewsRepository
from app.db.schema import news_events
from app.ingest.news import MockNewsCollector, NewsArticle, NewsIngestor

NOW = datetime(2026, 3, 25, 9, 0, tzinfo=UTC)


def test_mock_collector_only_returns_articles_since_the_given_time() -> None:
    collector = MockNewsCollector(
        [
            NewsArticle(
                source="mock", external_id="a1", event_time=NOW - timedelta(days=2), headline="old"
            ),
            NewsArticle(
                source="mock", external_id="a2", event_time=NOW - timedelta(hours=1), headline="new"
            ),
        ]
    )
    result = collector.fetch_latest(since=NOW - timedelta(days=1))
    assert [a.external_id for a in result] == ["a2"]


def test_news_ingestor_writes_through_repository_idempotently(migrated_schema, db_session) -> None:
    collector = MockNewsCollector(
        [NewsArticle(source="mock", external_id="a1", event_time=NOW, headline="headline one")]
    )
    ingestor = NewsIngestor(collector, NewsRepository(db_session), clock=lambda: NOW)

    first = ingestor.run(since=NOW - timedelta(days=1))
    second = ingestor.run(since=NOW - timedelta(days=1))  # same source data again

    assert first.attempted == 1
    assert second.attempted == 1

    count = db_session.execute(select(func.count()).select_from(news_events)).scalar_one()
    assert count == 1
