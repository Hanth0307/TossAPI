"""Disclosure (e.g. DART) collector interface + a deterministic mock,
plus the ingestor that writes filings through
`app.db.repositories.disclosure`. See `app.ingest.news` for the same
pattern applied to news - no real DART API is integrated yet.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.db.repositories.disclosure import DisclosureRepository
from app.ingest.results import IngestResult


@dataclass(frozen=True)
class DisclosureFiling:
    source: str
    external_id: str
    event_time: datetime
    title: str
    filing_type: str | None = None
    instrument_id: int | None = None
    raw_payload: dict[str, Any] | None = None


class DisclosureCollector(Protocol):
    def fetch_latest(self, *, since: datetime) -> list[DisclosureFiling]: ...


class MockDisclosureCollector:
    """In-memory, deterministic - no network call."""

    def __init__(self, filings: Sequence[DisclosureFiling] | None = None) -> None:
        self._filings: list[DisclosureFiling] = list(filings or [])

    def add_filing(self, filing: DisclosureFiling) -> None:
        self._filings.append(filing)

    def fetch_latest(self, *, since: datetime) -> list[DisclosureFiling]:
        return [f for f in self._filings if f.event_time >= since]


class DisclosureIngestor:
    def __init__(
        self,
        collector: DisclosureCollector,
        repository: DisclosureRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._collector = collector
        self._repository = repository
        self._clock = clock

    def run(self, *, since: datetime) -> IngestResult:
        filings = self._collector.fetch_latest(since=since)
        now = self._clock()
        rows = [
            {
                "source": filing.source,
                "external_id": filing.external_id,
                "instrument_id": filing.instrument_id,
                "event_time": filing.event_time,
                "available_at": now,
                "ingested_at": now,
                "title": filing.title,
                "filing_type": filing.filing_type,
                "raw_payload": filing.raw_payload,
            }
            for filing in filings
        ]
        upserted = self._repository.upsert_disclosures(rows)
        source = filings[0].source if filings else "disclosure"
        return IngestResult(source=source, attempted=len(rows), upserted=upserted)
