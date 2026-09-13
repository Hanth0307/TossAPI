# ADR 0011: AI Context, Quant Model, Market Regime, and the Signal Engine

## Status
Accepted (Phase 05)

## Context
Phase 04 gave the platform a way to narrow the market down to
candidates with real, structured evidence attached. Phase 05 adds the
AI/quant layer that evidence feeds into - and the phase explicitly
requires keeping two very different kinds of reasoning apart: an LLM's
job is to explain *why* a news/disclosure item might matter (entity,
event type, impact shape), never to output a trading probability by
itself; a numeric model's job is to turn price/volume/market-state
history into a calibrated probability, never to read text. Collapsing
these into one "the AI says buy" score would hide exactly the
distinction the phase asks for, so this phase is built as four
separate packages that only meet inside `app.signals`, and even there
produce structured evidence, not an order.

## Decision

### AI Context (`app.ai_context`) - a fixed schema, isolated LLM call
`schema.py` defines two deliberately separate types:

- `LLMContextOutput` (pydantic) - the exact shape an LLM is constrained
  to produce, passed as `output_format=LLMContextOutput` to
  `client.messages.parse` (Claude API structured outputs -
  `claude_extractor.py`). It covers every field the phase asks for:
  entity links (with a `match_status` that is never guessed toward
  "matched" - an unconfident entity gets `unmatched`/`ambiguous` and
  no ticker), `event_type`, `impact_direction` (direct/indirect),
  `impact_duration` (one-off/structural), `novelty` (new/duplicate/
  follow-up, with a `duplicate_cluster_id` for clustering repeated
  coverage), `source_reliability`, and a structured `impact_horizon`
  covering exactly the four required periods (1 day/5 day/10 day/
  long-term), each with its own direction and confidence.
- `AIContextResult` (a frozen dataclass, this codebase's `*Row`
  convention) - what every extractor actually returns. It is flat and
  **total**: every field always has a value. A failed or unparseable
  LLM response produces the *same* shape with every classification
  field at its explicit `UNKNOWN` variant, `status=unknown`, and
  `parse_error` set - never a `None` a caller could mistake for "the
  model said nothing," never a raised exception, and never a guessed
  value standing in for a real one.

Isolation mirrors `app.research.tradingview_mcp`'s established
pattern: `ClaudeContextExtractor.extract` wraps the entire API call in
a broad `except Exception` and converts any failure (network, auth,
rate limit, a response that fails schema validation) into an
`unknown_result()`. `MockContextExtractor` shares the exact same
`ok_result`/`unknown_result` helpers (`extractor.py`), so a test
written against the mock exercises the identical contract a caller
sees against the real extractor - see
`tests/ai_context/test_schema_and_extractors.py`.

Persistence (`app.ai_context.persistence`, the only place this
package touches `app.db`) writes to a new `ai_context_annotations`
table, keyed on `(source, external_id, event_kind, model_name,
model_version)`. This uses the plain observed-event upsert pattern
(`app.db.upsert.upsert_event_rows`), not the append-only revision
pattern ADR 0009 introduced for `market_bars`/`news_events`/
`disclosure_events`: an AI Context annotation is a *derived*
interpretation recomputed from immutable source text, not an
externally-issued correction to a fact, so the revision-history
complexity ADR 0009 reserves for genuinely correctable data would be
needless here (the same reasoning ADR 0009 already applied to
`instruments`). `available_at` is set to the moment the annotation was
generated (never backdated to the source article's own `event_time`),
so a point-in-time read can never see an annotation before it actually
existed - proven in `tests/ai_context/test_persistence.py`.

### Market Regime (`app.regime`) - pure classification, as_of-gated fetch
`classifier.py::RegimeClassifier` is pure logic over an already-fetched
bar list (plus optional advance/decline counts for breadth) - trend
(uptrend/downtrend/sideways, from return-over-lookback vs. threshold),
volatility (low/normal/high, from trailing realized volatility vs.
threshold), and breadth (expanding/contracting/neutral, from an
advancing/declining ratio vs. threshold). Every threshold is a
required constructor argument - nothing is hardcoded, matching
`app.scanners.universe`'s discipline. A dimension that cannot be
computed (not enough bars, no breadth counts supplied) reports
`UNKNOWN` with a reason, never a guessed default.

**"Regime never uses future data" is a composition property, not a
guard inside the classifier.** `RegimeClassifier` only ever looks at
the exact list it's handed - `tests/regime/test_classifier.py::
test_classifier_never_looks_beyond_the_bars_it_is_given` proves this
directly. `provider.py::RegimeProvider` is the only place this package
touches `app.db`, fetching through `MarketBarRepository.
get_bars_as_of` (the same `as_of`-gated method the Scanner pipeline
uses) - so the composition of the two inherits the leak-free guarantee
`tests/db/test_point_in_time_correction.py` proves at the repository
layer, reproduced end to end in
`tests/regime/test_provider_integration.py` with the identical
correction scenario ADR 0009 introduced (a flat original bar, a later
sharp-rally correction): a regime assessed before the correction's
`available_at` sees the original value, one assessed after sees the
correction.

### Quant Model (`app.models`) - baseline first, leakage prevented structurally
**Label**: `labels.py::compute_forward_return_label` - a fixed
N-trading-day (default baseline: 5) forward return, thresholded into a
binary label (`1` iff the forward return strictly exceeds
`return_threshold`; `0` otherwise). Both `horizon_days` and
`return_threshold` are explicit fields on `LabelDefinition` -
`return_threshold=0` gives "did the price go up," a nonzero threshold
gives an excess-return label, and both are recorded on the trained
model's artifact for reproducibility, matching the phase's "5-day
up-move or excess return or a predefined label" requirement.

**Features**: `features.py::compute_features` - a fixed, versioned
schema (`FEATURE_SCHEMA_VERSION`, `FEATURE_NAMES`): returns over 1/5/
10/20-day lookbacks, 20-day realized volatility, a 5-day-vs-20-day
volume ratio, and price-vs-20-day-SMA. A feature vector is only ever
produced with the full fixed set filled in (never a partially-filled
vector with a fabricated zero standing in for missing history) -
insufficient history returns `None` with a reason instead.

**Leakage prevention is structural, not a reviewable convention**:
`dataset.py::DatasetBuilder` fetches a sample's features and its label
from two separate `MarketBarRepository.get_bars_as_of` calls with
disjoint date ranges - the feature fetch ends at `as_of`
(`event_time <= as_of`, exactly the repository's own point-in-time
guarantee), the label fetch starts at `as_of` and looks forward,
gated by a separately-supplied `data_as_of` cutoff that makes explicit
this is training-set construction, not live inference. There is no
code path that could pass one list to both.
`tests/models/test_dataset_leakage.py::
test_feature_vector_is_identical_regardless_of_what_the_label_window_holds`
proves this directly: two instruments with identical feature-window
history but wildly different (and oppositely labeled) label-window
futures produce byte-identical feature vectors. A second test in the
same file reproduces the ADR 0009 correction scenario for the *label*
side specifically.

**Train/validation order**: `training.py::time_ordered_split` sorts by
`as_of` and never shuffles - every train sample's `as_of` precedes
every validation sample's. The same discipline extends into model
fitting itself: `model.py::BaselineQuantModel` calibrates via
`sklearn.calibration.CalibratedClassifierCV` with a `TimeSeriesSplit`
internal CV (never a shuffled K-fold), so "preserve chronological
order" holds at both the outer split and the calibration step inside
it.

**Model**: L2-regularized logistic regression, deliberately the
simplest model that produces a genuinely calibrated probability - the
phase's "build the baseline first" requirement taken literally. It
also fills in Phase 00's `app.models.base.SignalModel` interface
(`BaselineQuantModel.predict` delegates to `predict_proba`).

**Evaluation** (`evaluation.py`) reports more than AUC, per the phase
spec: `ClassificationMetrics` bundles AUC, PR-AUC, precision/recall at
an explicit decision threshold, Brier score, Expected Calibration
Error (a 10-bin reliability-curve summary), and the positive-class
rate (class balance) together, so none of these can be read in
isolation from the others. `compute_metrics_by_group` produces the
same bundle broken out by any caller-supplied key - used for both
per-period (e.g. by month) and per-regime (by `RegimeAssessment.
trend`, joined in by the caller) reporting, keeping this module
independent of `app.regime`.

**Explainability as a validation aid, not a primary output**:
`importance.py` uses `sklearn.inspection.permutation_importance`
rather than SHAP - it answers the same practical question ("which
features does the model's held-out accuracy actually depend on")
without adding a heavy dependency for a baseline model, and the phase
asks for this only "as 검증 보조" (a validation aid). Nothing in
training or model selection reads a `FeatureImportance` value.

**Artifact storage**: the fitted estimator is serialized with
`joblib` to a file; everything needed to reproduce or audit the run -
feature schema version and names, the label definition, hyperparameters,
train/validation sample counts and the split boundary, and the full
evaluation-metrics bundle (validation + by-period + by-regime) - is
recorded on the existing Phase 03 `model_runs` table (`params`/
`metrics`, both already JSONB). No new migration was needed for this.
Two training runs under different `model_version`s produce distinct,
independently-addressable `model_runs` rows - the same guarantee
`tests/scanners/test_pipeline_integration.py` proved for
`strategy_version` in Phase 04, reproduced here in
`tests/models/test_artifact.py::
test_persist_training_run_records_distinguishable_rows_per_model_version`.

### Signal Engine (`app.signals`) - structure only, never an order
`schema.py::SignalInput` bundles `ai_context: list[AIContextResult]`,
an optional `QuantProbability`, and an optional `RegimeAssessment` for
one `(instrument, as_of)`. A missing input is an empty list / `None` -
never a fabricated placeholder - so a downstream consumer can always
tell "this input wasn't available" from "this input said X"
(`has_ai_context`/`has_quant_probability`/`has_regime` make this
explicit). `engine.py::SignalEngine` is the only place this package
touches `app.db`: it computes the quant probability itself (from
`as_of`-gated bars, through the same `compute_features` the training
pipeline uses) and the regime assessment itself (through
`RegimeProvider`), but **takes AI Context as a caller-supplied list**
rather than deciding "which news items are relevant to this
instrument" internally - that judgment call (symbol matching, lookback
window, dedup handling) belongs with whoever assembles a signal run,
not baked into the engine.

**Nothing in this package generates an order.** `SignalInput` has no
side/quantity/order_type/price-shaped field
(`tests/signals/test_schema.py::
test_signal_input_never_has_an_order_shaped_field` checks this
directly), and `app.signals` has no import edge to `app.brokers` or
`app.execution` (`tests/signals/test_isolation.py`) - the same
structural guarantee `app.scanners.candidate.Candidate` established
for the Scanner layer in Phase 04, extended here to the combined AI/
quant/regime evidence a later phase will eventually turn into a
strategy.

## Consequences
- AI Context and the Quant Model can be developed, evaluated, and
  swapped independently - the LLM never sees price data, the numeric
  model never sees article text, and a `SignalInput` records
  separately whether each was even available for a given assessment.
- A `ClaudeContextExtractor` outage degrades to explicit `unknown`
  annotations, never a pipeline failure - callers can always fall back
  to `MockContextExtractor` for tests or offline runs with identical
  behavior.
- Retraining the quant model under a new `model_version` never
  overwrites a prior run's artifact or metrics - every training run is
  independently addressable and auditable.
- Phase 06 (Backtest) consumes `app.signals.schema.SignalInput` as its
  primary input type, plus directly `app.scanners.candidate.Candidate`
  where narrower Scanner-only backtesting is wanted - neither this
  phase nor Phase 04 needs to change for that; Phase 06 only adds a
  new package that reads both.
