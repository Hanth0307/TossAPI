"""Market Regime (Phase 05): trend / volatility / breadth
classification from already `as_of`-fetched benchmark bars. See
docs/architecture/0011-ai-context-quant-regime-signal-engine.md.

Depends on `app.core` and `app.db` only. `classifier.py` is pure logic
- no database import, so every trend/volatility/breadth dimension is
fixture-testable with no database at all (`tests/regime/
test_classifier.py`). `provider.py` is the sole place this package
touches `app.db` - it reads through `MarketBarRepository.
get_bars_as_of` (`as_of`-gated), so a regime assessment can never use
a bar that was not yet available at the point in time it is assessing.

**A `RegimeAssessment` never uses future data.** `RegimeClassifier`
only ever looks at the window it is handed - it is the caller's job
(here, `RegimeProvider`) to fetch that window `as_of`-gated, and
`tests/regime/test_provider_integration.py` proves the two compose
correctly (a bar available only after `as_of` never changes a past
assessment).
"""
