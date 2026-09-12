# ADR 0010: Scanner pipeline (Market -> Universe Filter -> Event Scanner -> Strategy Scanner -> Candidate)

## Status
Accepted (Phase 04)

## Context
Phase 03 gave the platform a point-in-time-correct data platform, but
no way to go from "everything in the database" to "instruments worth a
closer look right now." That narrowing has to happen in stages -
cheap, broad filters first (is this even tradable), then event
detection (did something unusual happen), then strategy-specific
conditions (does this match a specific researched idea) - and every
stage has to stay exactly as leak-free as the repositories it reads
from, since a scanner is exactly the kind of component that gets
re-run against historical data for backtesting and would otherwise
silently reintroduce a point-in-time leak Phase 03 just closed.

It also has to avoid two specific temptations this codebase has
consistently refused elsewhere: inventing a value for data nobody has
confirmed the shape of (ADR 0007's `UnparsedRecord`/never-guess-a-
field discipline), and treating a passing scan as an actual trading
decision.

## Decision

### Pipeline shape
`app/scanners` implements exactly the four stages the phase asked for:

1. **Market** (`InstrumentRepository.list_all`) - every known
   instrument, optionally narrowed to one exchange. Not `as_of`-gated:
   `instruments` is reference/master data (ADR 0009's scope decision),
   not a point-in-time observation.
2. **Universe Filter** (`app/scanners/universe.py`) - a `UniverseFilter`
   Protocol with `evaluate(UniverseFilterInput) -> UniverseFilterResult`.
   `LiquidityFilter`, `PriceRangeFilter`, and `RawFlagFilter` are the
   concrete filters shipped now. Every numeric threshold is a
   constructor argument - nothing is hardcoded - so the same filter
   class is reused with different limits per strategy/market/run.
3. **Event Scanner** (`app/scanners/events.py`) - an `EventScannerPlugin`
   Protocol with `detect(EventScanInput) -> EventDetection`, each
   plugin carrying a `market: str | None` field. `ScannerPipeline`
   only runs a plugin against an instrument when the plugin's `market`
   is `None` (market-agnostic) or equals the instrument's `exchange` -
   this is the mechanism for keeping Korean/US-specific rules separate
   without a parallel class hierarchy. Shipped plugins:
   `PriceGapEventScanner`, `AbnormalVolumeEventScanner`,
   `VolatilitySpikeEventScanner`, `NewsOccurrenceEventScanner`,
   `DisclosureOccurrenceEventScanner`, `OrderbookImbalanceEventScanner`
   (수급 변화, via bid/ask volume imbalance).
4. **Strategy Scanner** (`app/scanners/strategy_rules.py`) - a
   `StrategyScanner.evaluate(StrategyRuleSet, feature_set=...)` that
   checks each `StrategyCondition` (`field`, `Comparator`, `threshold`)
   against a `FeatureSet` and records a `StrategyConditionResult` per
   condition: PASS/FAIL, the actual observed value, and a failure
   reason when it fails. A condition whose `field` is missing from the
   `FeatureSet` is recorded as FAIL with an explicit reason - it is
   never treated as a pass, and no value is guessed for it.

`app/scanners/pipeline.py::ScannerPipeline` wires these together with
staged gating, cheapest/most-selective first: Universe Filter results
are always computed; if an instrument fails, its `Candidate` is
produced immediately and news/disclosures/orderbook are never fetched
for it. If it passes, Event Scanner plugins applicable to its market
run; if none trigger (and at least one plugin was configured), its
`Candidate` is produced immediately and the Strategy Scanner never
runs. Only when an event triggers (or no event scanners were
configured at all, a deliberate pass-through) is a `FeatureSet` built
and the optional `StrategyRuleSet` evaluated.

### Why `StrategyRuleSet` is not derived from `StrategySpec`
`app.research.models.StrategySpec.entry_rules`/`exit_rules` (Phase 01,
ADR 0006) are free-text research documentation - never parsed as
executable logic. `app.scanners.strategy_rules.StrategyRuleSet` is a
deliberately separate, structured, human-authored companion that
references the same `(strategy_id, strategy_version)` for
traceability. Turning a research idea into a machine-checkable
condition is an authoring step a person performs, not an automatic
inference this package makes - consistent with this codebase's
standing rule against inventing meaning for something nobody has
explicitly specified.

### The `Candidate` schema
`app/scanners/candidate.py::Candidate` is the pipeline's sole output -
never a bare ticker list:

```python
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
```

Every condition at every stage carries its own PASS/FAIL, the observed
value, and (on failure) a reason - `UniverseFilterResult`,
`EventDetection`, and `StrategyConditionResult` all follow this same
shape. `qualified` is a single boolean summary computed once by
`ScannerPipeline`, but **nothing in this codebase reads it as
authorization to place an order** - `app.brokers`/`app.execution`
remain interface-only (Phase 00) regardless of what it says.

### No fabricated sentiment
`NewsOccurrenceEventScanner`/`DisclosureOccurrenceEventScanner` detect
existence/count only ("did at least N items appear in this window").
There is no AI/sentiment model in this codebase yet, and this phase
does not fabricate one to stand in for it - a future Phase 05 model can
replace or extend these with a real score once one exists.

### Persistence and the Phase 05 interface
`app/scanners/persistence.py::persist_scan_results` writes one
`model_runs` row (via `ModelRunRepository.start_run`, keyed by
`strategy_id` + `strategy_version` + an optional `idempotency_key`)
and one `signals` row per candidate (via `SignalRepository.
upsert_signals`), then finishes the run with summary metrics. Because
`model_runs` rows are keyed by `strategy_version`, re-running the same
scan under a new version never overwrites the old run's `signals` -
they carry distinct `model_run_id`s - see
`tests/scanners/test_pipeline_integration.py::
test_strategy_version_segregation__distinct_model_runs_and_signals`.

What Phase 05 (AI/quant models) is expected to consume:
- `app.scanners.features.FeatureSet` - the named-`Decimal`-value
  currency between an Event Scanner's observations and a Strategy
  condition, carrying `as_of`/`data_source` so a future model can
  always tell which point-in-time view produced it.
- `app.scanners.events.EventDetection` - one observation per event
  plugin, with its own `observed_value`/`threshold`/`reason`.
- `app.scanners.candidate.Candidate` - the full per-instrument record,
  for a model that wants to condition on Universe/Event/Strategy
  history rather than only the latest `FeatureSet`.
- `app.db.repositories` directly, `as_of`-gated, for anything a model
  needs that this phase's scanners don't already compute.

None of these interfaces import anything from a hypothetical Phase 05
package - the dependency direction stays one-way (`scanners -> core,
db`; see ADR 0001).

### Module boundary
`app/scanners` depends on `core` and `db` only - no import edge to
`toss`, `research`, `ingest`, `brokers`, `risk`, or `execution` (see
`tests/scanners/test_isolation.py`). Within the package,
`universe.py`/`events.py`/`strategy_rules.py`/`candidate.py`/
`features.py` are pure logic over already-fetched data (no `sqlalchemy`
or `app.db.engine`/`app.db.upsert` import), so every filter/event/
condition is fixture-testable with no database at all; only
`pipeline.py` and `persistence.py` touch `app.db`, and every fetch they
make goes through an `app.db.repositories` `as_of`-gated method - the
pipeline never queries a table directly, so it inherits the leak-free
guarantee `tests/db/test_point_in_time_correction.py` proves for the
repository layer itself.

## Consequences
- A scan re-run against a historical `as_of` is provably unaffected by
  data that became available afterward - `tests/scanners/
  test_pipeline_integration.py::
  test_future_correction_leakage_regression__*` reproduces the exact
  correction scenario from ADR 0009 (a low-volume original bar, a
  higher-volume correction) and asserts a Universe Filter's PASS/FAIL
  flips only once `as_of` crosses the correction's `available_at`.
- Every `UniverseFilter`/`EventScannerPlugin` is instantiated with
  explicit, non-defaulted numeric thresholds; there is no built-in
  "reasonable default" anywhere in `app/scanners` for a filter/event
  threshold to fall back on, so a strategy/market/run's parameters
  always come from its own configuration, never from scanner code.
- Adding a new Korean- or US-specific event rule is a new
  `EventScannerPlugin` with `market="KR"`/`market="US"` passed to
  `ScannerPipeline`'s `event_scanners` list - no branching inside the
  pipeline itself, and no change to any other plugin.
- Extending the Strategy Scanner with a new condition type is a new
  `Comparator` case, not a new code path through `FeatureSet`/
  `Candidate` - Phase 05 can add features without either changing.
