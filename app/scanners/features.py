"""FeatureSet: the named-value currency between Event Scanner
observations and Strategy Scanner conditions - and the interface
Phase 05 (AI/quant models) is expected to consume computed features
through, without needing to know how each value was derived.

A FeatureSet is built once per (instrument, as_of) by
`app.scanners.pipeline.ScannerPipeline` from already as_of-filtered
data - it carries `as_of`/`data_source` alongside the values themselves
so any downstream consumer (a Strategy condition, a future model) can
tell exactly which point-in-time view produced them, per ADR 0008/0009.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class FeatureSet:
    instrument_symbol: str
    as_of: datetime
    data_source: str
    values: dict[str, Decimal] = field(default_factory=dict)

    def get(self, name: str) -> Decimal | None:
        return self.values.get(name)
