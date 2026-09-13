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
strategies  -> core, data, models
backtest    -> core, data, strategies
brokers     -> core, adapters
risk        -> core, brokers        (only for the OrderRequest type)
execution   -> core, brokers, risk
research    -> core                                   (added Phase 01, see ADR 0006)
toss        -> core, adapters                         (added Phase 02, see ADR 0007)
db          -> core                                  (added Phase 03, see ADR 0008)
ingest      -> core, db, toss, data, research         (added Phase 03, see ADR 0008)
scanners    -> core, db                               (added Phase 04, see ADR 0010)
models      -> core, db                               (Quant Model, Phase 05, see ADR 0011)
ai_context  -> core, db                               (added Phase 05, see ADR 0011)
regime      -> core, db                               (added Phase 05, see ADR 0011)
signals     -> core, db, ai_context, models, regime   (added Phase 05, see ADR 0011)
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
- `research` depends on `core` only, and specifically never on
  `brokers`/`risk`/`execution` - a strategy research artifact
  (`StrategySpec`) can never be one import away from placing an order.
  See ADR 0006.
- `toss` (the concrete Toss Open API integration) depends on `core`
  and `adapters` only, and specifically never on `research` - a Toss
  API outage cannot affect strategy research, and a TradingView MCP
  outage (ADR 0006) cannot affect this gateway. `toss` also has no
  order-mutating capability at all: see ADR 0007.
- `db` (schema, migrations, repositories) depends on `core` only - it
  has no import edge to `toss`, `research`, `brokers`, `risk`, or
  `execution`. It only stores and queries rows; it never fetches
  anything itself. `ingest` is the one package allowed to depend on
  `db`, `toss`, `data`, and `research` together - it is where "fetch
  from an external source" and "write through a repository" meet, and
  nothing depends on `ingest` in return. See ADR 0008.
- `scanners` (Phase 04's Universe/Event/Strategy scanner pipeline)
  depends on `core` and `db` only - it has no import edge to `toss`,
  `research`, `ingest`, `brokers`, `risk`, or `execution`. It reads
  exclusively through `app.db.repositories`'s `as_of`-gated methods
  and never calls an external API itself; a `Candidate` it produces is
  a research artifact, never an order. See ADR 0010.
- `models` (Phase 05's Quant Model baseline), `ai_context` (Phase 05's
  LLM-based news/disclosure classification), and `regime` (Phase 05's
  Market Regime classifier) each depend on `core` and `db` only - none
  has an import edge to `toss`, `research`, `ingest`, `scanners`,
  `brokers`, `risk`, or `execution`, and critically, none of the three
  imports either of the other two: an LLM never sees price data and a
  numeric model never sees article text. `signals` is the one package
  allowed to depend on all three together plus `db` - it is where "AI
  Context, Quant probability, and Regime meet," and, like `scanners`,
  produces a structured research artifact (`SignalInput`) that is
  never an order - it has no import edge to `brokers`/`execution`
  either. See ADR 0011.
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
