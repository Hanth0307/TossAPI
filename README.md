# AI Quant Trading Platform

Modular skeleton for an AI-assisted quant trading platform: Toss
Investment Open API integration, news/DART ingestion, market scanners,
AI/quant signal models, backtesting, a paper broker, a risk engine,
and order execution.

**Phase 00 (this phase): project skeleton only.** No trading strategy,
AI model, or live order-placing code is implemented. Everything under
`app/{scanners,models,strategies,backtest,brokers,risk,execution}` is
an interface (`base.py`, `abc.ABC`) with no concrete logic yet, so
later phases can build on stable module boundaries without having to
rewrite this scaffolding.

## Module map and dependency direction

```
core        <- (everything; core imports nothing else under app/)
adapters    -> core
data        -> core, adapters
scanners    -> core, data
models      -> core
strategies  -> core, data, models
backtest    -> core, data, strategies
brokers     -> core, adapters
risk        -> core, brokers        (OrderRequest type only)
execution   -> core, brokers, risk
```

| Package | Responsibility |
|---|---|
| `app/core` | Settings (`config.py`), structured logging (`logging.py`), exception hierarchy (`exceptions.py`) |
| `app/adapters` | Common outbound-HTTP timeout/retry policy (`http_client.py`) |
| `app/data` | Market data / news / disclosure provider interfaces |
| `app/scanners` | Symbol scanning/filtering interface |
| `app/models` | AI/quant signal model interface |
| `app/strategies` | Strategy interface (market data + signals -> order intents) |
| `app/backtest` | Backtest engine interface |
| `app/brokers` | Broker adapter interface (paper/live) - no real order calls |
| `app/risk` | Risk engine interface - gates every order before a broker sees it |
| `app/execution` | Orchestrates risk check + broker submission for one order |

See `docs/architecture/` for the design decisions (ADRs) behind this
structure, in particular:
- `0001-module-boundaries.md` - why these boundaries and this
  dependency direction
- `0002-config-and-secrets.md` - environment/secret handling
- `0003-logging-and-exceptions.md` - structured logging, exception
  hierarchy
- `0004-external-api-timeout-retry-policy.md` - **why order calls use
  a separate, non-retrying policy**
- `0005-testing-and-tooling.md` - pytest/ruff/mypy setup

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# edit .env with real values - never commit it
```

## Running tests

```bash
make test
# or: pytest --cov=app --cov-report=term-missing
```

## Lint / type-check

```bash
make lint       # ruff check .
make typecheck  # mypy app
make check       # lint + typecheck + test
```

## Local PostgreSQL (optional, for a later phase)

```bash
docker compose up -d db
```

No application code depends on PostgreSQL yet; this just prepares the
local infrastructure for when a persistence layer is added.

## Safety notes

- `PAPER_TRADING_ONLY=true` is the hard default in `.env.example`.
- No code path in this repository calls a real broker's order-placing
  endpoint. `app/brokers/base.py` and `app/execution/base.py` are
  interfaces only (`abstractmethod`, cannot be instantiated directly -
  see `tests/brokers/test_base.py` / `tests/execution/test_base.py`).
- Order-mutating calls, once implemented, must use
  `app.adapters.http_client.NO_RETRY_POLICY` rather than the default
  retrying policy - see ADR 0004.
- No API response field name in this codebase is guessed. Provider
  interfaces in `app/data/base.py` return untyped payloads on purpose,
  pending verification against each real API's actual responses.

## Roadmap

- **Phase 00 (done)**: this skeleton - config, logging, exceptions,
  HTTP timeout/retry policy, module interfaces, tests, tooling.
- **Phase 01+**: concrete Toss API adapter (read-only endpoints
  first), a paper broker implementation, a first scanner, and a first
  backtest engine implementation - each phase should only need to fill
  in a `base.py` interface defined here, not change these boundaries.
