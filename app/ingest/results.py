"""Shared result type every ingestor in this package returns."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestResult:
    source: str
    attempted: int
    upserted: int
