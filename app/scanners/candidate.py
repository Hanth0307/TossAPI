"""Candidate: the Scanner pipeline's output - never an order, a buy
signal, or a trade instruction.

A `Candidate` bundles every stage's evidence (Universe Filter results,
Event Scanner detections, and an optional Strategy Scanner result) for
one instrument at one `as_of` point in time, so a human or a later
phase can see exactly *why* an instrument reached (or failed to reach)
each stage - never just a bare ticker symbol.

`qualified` is a plain boolean summary of "passed every stage that ran
for it" - `app.scanners.pipeline.ScannerPipeline` computes it once, and
nothing anywhere in this codebase reads it as authorization to place an
order. `app.brokers`/`app.execution` remain interface-only (Phase 00)
regardless of what a Candidate says.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.scanners.events import EventDetection
from app.scanners.strategy_rules import StrategyScanResult
from app.scanners.universe import UniverseFilterResult


@dataclass(frozen=True)
class Candidate:
    instrument_id: int
    symbol: str
    exchange: str
    as_of: datetime
    data_source: str
    universe_results: list[UniverseFilterResult]
    event_detections: list[EventDetection]
    strategy_result: StrategyScanResult | None
    qualified: bool
    generated_at: datetime

    @property
    def passed_universe(self) -> bool:
        return all(result.passed for result in self.universe_results)

    @property
    def has_triggering_event(self) -> bool:
        return any(detection.detected for detection in self.event_detections)

    @property
    def passed_strategy(self) -> bool:
        if self.strategy_result is None:
            return False
        return self.strategy_result.passed
