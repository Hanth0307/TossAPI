# ADR 0001: Module boundaries and dependency direction

## Status
Accepted (Phase 00)

## Context
The platform will grow to include Toss API integration, news/DART
ingestion, scanners, AI/quant models, backtesting, a paper broker,
a risk engine, and order execution. Without an agreed dependency
direction, these modules tend to become tangled (e.g. a strategy
importing a broker directly, or the risk engine depending on a
specific broker implementation), which makes each piece hard to test
or replace in isolation.

## Decision
Top-level packages under `app/` and their allowed dependency direction
(an arrow means "may import from"):

```
core        <- (everything; core imports nothing else under app/)
adapters    -> core
data        -> core, adapters
scanners    -> core, data
models      -> core
strategies  -> core, data, models
backtest    -> core, data, strategies
brokers     -> core, adapters
risk        -> core, brokers        (only for the OrderRequest type)
execution   -> core, brokers, risk
```

Rules:
- `app.core` (config, logging, exceptions) has zero dependents inside
  `app/` upward - every other package may depend on it, it depends on
  none of them.
- A package may only import from packages listed as its dependencies
  above. In particular, `strategies` and `backtest` must never import
  `brokers`, `risk`, or `execution` - a backtest must be runnable with
  no broker present at all.
- `execution` is the only package allowed to call both `risk` and
  `brokers` together; this is what enforces "every order passes risk
  checks before reaching a broker" as a structural property, not just
  a convention.
- Each package's `__init__.py` states its allowed dependencies in a
  docstring, so the boundary is visible from the file itself.

## Consequences
- Backtesting, strategy development, and scanner work can proceed
  fully decoupled from broker/execution code, which does not exist
  yet as a live implementation.
- A future live broker adapter only touches `app.brokers`; it cannot
  accidentally bypass `app.risk` because `app.strategies` never talks
  to `app.brokers` directly.
- This is enforced by convention/code review in Phase 00 (no import
  linter is configured yet). If violations become common, consider
  adding an import-boundary lint rule (e.g. `ruff`'s `TID` rules or
  `import-linter`) in a later phase.
