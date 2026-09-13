"""AI / quantitative model interfaces (signal generation).

Phase 05 fills in the Quant Model side of `app.models.base.
SignalModel` with a baseline logistic-regression-plus-calibration
model (`BaselineQuantModel`) - see docs/architecture/
0011-ai-context-quant-regime-signal-engine.md. Depends on `app.core`
and `app.db` only (`app.db.repositories.market_data.
MarketBarRepository`, `as_of`-gated, for feature/label bar fetches;
`app.db.repositories.runs.ModelRunRepository`, for artifact metadata).

`labels.py`/`features.py`/`model.py`/`training.py`/`evaluation.py`/
`importance.py` are pure logic (no database import) - only
`dataset.py` (fetches bars) and `artifact.py` (persists a training
run) touch `app.db`, mirroring `app.scanners`'s pipeline/persistence
split.

**Leakage prevention is structural, not a convention someone could
forget**: `app.models.dataset.DatasetBuilder` fetches features and
labels from two separate `MarketBarRepository.get_bars_as_of` calls
with disjoint date ranges, and `app.models.training.
time_ordered_split` never shuffles - see each module's docstring and
`tests/models/test_dataset_leakage.py`.

**No sentiment/quality score is invented here either** - see
`app.ai_context` for the LLM-side complement to this package, kept
deliberately separate (this package never asks an LLM anything, and
`app.ai_context` never computes a numeric trading probability).
"""
