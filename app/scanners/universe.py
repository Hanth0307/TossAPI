"""Universe Filter: narrows "every known instrument" down to a
tradable universe based on liquidity/turnover/price-range/status
checks.

Pure logic - every filter operates on data already fetched (and
already `as_of`-filtered) by the caller, typically
`app.scanners.pipeline.ScannerPipeline`. No filter here queries a
database itself, so each one is testable with a fixed fixture and no
as_of-correctness burden of its own - see `tests/scanners/
test_universe_filters.py`.

Numeric thresholds are always constructor arguments, never hardcoded
in a filter's logic, so the same filter class can be reused with
different limits per strategy/market/run.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from app.db.repositories.market_data import InstrumentRow, MarketBarRow


@dataclass(frozen=True)
class UniverseFilterInput:
    instrument: InstrumentRow
    recent_bars: list[MarketBarRow]


@dataclass(frozen=True)
class UniverseFilterResult:
    filter_name: str
    passed: bool
    observed_value: Any
    threshold: Any | None
    reason: str | None


class UniverseFilter(Protocol):
    @property
    def name(self) -> str: ...

    def evaluate(self, data: UniverseFilterInput) -> UniverseFilterResult: ...


@dataclass(frozen=True)
class LiquidityFilter:
    """PASS when average daily turnover (`close_price * volume`,
    averaged over the supplied bars) is at least `min_turnover_value`.
    """

    min_turnover_value: Decimal
    name: str = "liquidity"

    def evaluate(self, data: UniverseFilterInput) -> UniverseFilterResult:
        if not data.recent_bars:
            return UniverseFilterResult(
                self.name, False, None, self.min_turnover_value, "no recent bars available"
            )
        turnovers = [bar.close_price * bar.volume for bar in data.recent_bars]
        avg_turnover = sum(turnovers) / len(turnovers)
        passed = avg_turnover >= self.min_turnover_value
        reason = (
            None if passed else f"average turnover {avg_turnover} < {self.min_turnover_value}"
        )
        return UniverseFilterResult(
            self.name, passed, avg_turnover, self.min_turnover_value, reason
        )


@dataclass(frozen=True)
class PriceRangeFilter:
    """PASS when the latest close_price falls within
    `[min_price, max_price]` (either bound may be `None` to mean
    unbounded on that side)."""

    min_price: Decimal | None
    max_price: Decimal | None
    name: str = "price_range"

    def evaluate(self, data: UniverseFilterInput) -> UniverseFilterResult:
        if not data.recent_bars:
            return UniverseFilterResult(
                self.name, False, None, (self.min_price, self.max_price), "no recent bars available"
            )
        latest = data.recent_bars[-1].close_price
        passed = True
        if self.min_price is not None and latest < self.min_price:
            passed = False
        if self.max_price is not None and latest > self.max_price:
            passed = False
        reason = (
            None
            if passed
            else f"close_price {latest} outside [{self.min_price}, {self.max_price}]"
        )
        return UniverseFilterResult(
            self.name, passed, latest, (self.min_price, self.max_price), reason
        )


class RawFlagStatus(StrEnum):
    PASS_ = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


def _lookup_path(payload: Any, field_path: str) -> Any:
    current = payload
    for part in field_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


@dataclass(frozen=True)
class RawFlagFilter:
    """Generic PASS/FAIL/UNKNOWN check against a field somewhere in
    `instrument.raw_payload` (dotted `field_path`) - e.g. a future
    trading-halt or 관리/주의 status flag, once Toss confirms the real
    field name for `/api/v1/stocks` (still `UnparsedRecord` per ADR
    0007 - `app.toss.market_data.MarketDataAdapter.get_stocks` does not
    assert any field names). If the field is absent, the result is
    UNKNOWN - never a guessed PASS or FAIL - because this filter must
    not invent meaning for a response shape nobody has confirmed yet.
    `treat_unknown_as_pass` decides whether missing data blocks the
    instrument (conservative default: `False`) or lets it through with
    the UNKNOWN noted in `reason` for audit.
    """

    field_path: str
    fail_values: frozenset[Any]
    treat_unknown_as_pass: bool = False
    name: str = "raw_flag"

    def evaluate(self, data: UniverseFilterInput) -> UniverseFilterResult:
        raw_payload = data.instrument.raw_payload
        if not raw_payload:
            status = RawFlagStatus.PASS_ if self.treat_unknown_as_pass else RawFlagStatus.FAIL
            return UniverseFilterResult(
                self.name,
                status == RawFlagStatus.PASS_,
                None,
                sorted(self.fail_values, key=str),
                f"no raw_payload available for field {self.field_path!r} (status={status.value})",
            )

        value = _lookup_path(raw_payload, self.field_path)
        if value is None:
            status = RawFlagStatus.PASS_ if self.treat_unknown_as_pass else RawFlagStatus.FAIL
            return UniverseFilterResult(
                self.name,
                status == RawFlagStatus.PASS_,
                None,
                sorted(self.fail_values, key=str),
                f"field {self.field_path!r} not present (status={status.value})",
            )

        passed = value not in self.fail_values
        reason = None if passed else f"{self.field_path}={value!r} is in fail_values"
        return UniverseFilterResult(
            self.name, passed, value, sorted(self.fail_values, key=str), reason
        )
