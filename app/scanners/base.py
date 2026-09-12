"""Scanner interface (Phase 00 skeleton, filled in by Phase 04's
`app.scanners.pipeline.ScannerPipeline`).

`scan` takes `as_of` explicitly - a Scanner implementation may only see
data available at that point in time (see `app.db.repositories` and
docs/architecture/0008-data-platform.md), and returns
`app.scanners.candidate.Candidate` objects, never bare symbols and
never an order.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.scanners.candidate import Candidate


class Scanner(ABC):
    """Produces `Candidate` research artifacts for one `as_of` point
    in time. No concrete scanning criteria are implemented here -
    see `app.scanners.pipeline.ScannerPipeline` for Phase 04's
    implementation."""

    @abstractmethod
    def scan(self, *, as_of: datetime) -> list[Candidate]:
        raise NotImplementedError
