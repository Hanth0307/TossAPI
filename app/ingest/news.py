"""News collector interface + a deterministic mock, plus the ingestor
that writes collected articles through `app.db.repositories.news`.

No real news API is integrated yet - `MockNewsCollector` is the stand-
in per "외부 서비스는 mock adapter부터 만든다". A real collector only
needs to implement `NewsCollector` (the `Protocol` below); nothing
else in this module changes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.db.repositories.news import NewsRepository
from app.ingest.results import IngestResult


@dataclass(frozen=True)
class NewsArticle:
    source: str
    external_id: str
    event_time: datetime
    headline: str
    body: str | None = None
    related_symbols: list[str] | None = None
    raw_payload: dict[str, Any] | None = None


class NewsCollector(Protocol):
    def fetch_latest(self, *, since: datetime) -> list[NewsArticle]: ...


class MockNewsCollector:
    """In-memory, deterministic - no network call. Seed it with
    `add_article` in a test or a dev script."""

    def __init__(self, articles: Sequence[NewsArticle] | None = None) -> None:
        self._articles: list[NewsArticle] = list(articles or [])

    def add_article(self, article: NewsArticle) -> None:
        self._articles.append(article)

    def fetch_latest(self, *, since: datetime) -> list[NewsArticle]:
        return [a for a in self._articles if a.event_time >= since]


class NewsIngestor:
    def __init__(
        self,
        collector: NewsCollector,
        repository: NewsRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._collector = collector
        self._repository = repository
        self._clock = clock

    def run(self, *, since: datetime) -> IngestResult:
        articles = self._collector.fetch_latest(since=since)
        now = self._clock()
        rows = [
            {
                "source": article.source,
                "external_id": article.external_id,
                "event_time": article.event_time,
                "available_at": now,
                "ingested_at": now,
                "headline": article.headline,
                "body": article.body,
                "related_symbols": article.related_symbols,
                "raw_payload": article.raw_payload,
            }
            for article in articles
        ]
        upserted = self._repository.upsert_news(rows)
        source = articles[0].source if articles else "news"
        return IngestResult(source=source, attempted=len(rows), upserted=upserted)
