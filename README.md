# AI Quant Trading Platform

Modular skeleton for an AI-assisted quant trading platform: Toss
Investment Open API integration, news/DART ingestion, market scanners,
AI/quant signal models, backtesting, a paper broker, a risk engine,
and order execution.

**Phase 00: project skeleton.** No trading strategy, AI model, or live
order-placing code is implemented. Everything under
`app/{scanners,models,strategies,backtest,brokers,risk,execution}` is
an interface (`base.py`, `abc.ABC`) with no concrete logic yet, so
later phases can build on stable module boundaries without having to
rewrite this scaffolding.

**Phase 01: Strategy Research Lab.** TradingView (+ Claude MCP) is
used strictly as a research tool - never as a live trading engine.
Strategy ideas are recorded as reproducible `StrategySpec` records in
a file-based Strategy Registry (`app/research`). See
`docs/research/strategy-research-lab-guide.md` for usage and
`docs/architecture/0006-strategy-research-lab.md` for the design.
TradingView output is never auto-approved and still cannot reach a
real order - `app/brokers`/`app/execution` remain interface-only.

**Phase 02: Toss Open API integration (read-only).** `app/toss`
connects to the real Toss Open API as a Market Data Gateway
(`/api/v1/{prices,orderbook,trades,price-limits,candles,stocks}`) and
a Portfolio Read Gateway (`/api/v1/{accounts,holdings,orders,
buying-power,sellable-quantity,commissions}`). The OAuth2 Client
Credentials *request*, per-endpoint rate limiting, and precise
401/403/429/5xx error mapping are all confirmed against the official
docs; the OAuth token *response* JSON schema was never shown and is
treated as an explicitly provisional/unverified adapter assumption,
isolated behind a swappable parser (`app/toss/token_parser.py`) that
fails closed on a mismatch. There is no order-placing code anywhere -
`TossRestClient` has no HTTP verb but `get()`, and
`Settings.toss_read_only_mode` gates construction. Toss also offers a
WebSocket API per its own marketing page, but no protocol detail has
been verified, so none is implemented (see status block in
`app/toss/market_data.py`). See
`docs/architecture/0007-toss-api-integration.md`.

**Phase 03: Data Platform.** `app/db` is a PostgreSQL schema (15
tables, `alembic`-migrated) + repository layer for instruments, market
bars/ticks/orderbook snapshots, news/disclosure events, the strategy
registry, signals, model/backtest runs, paper/broker orders,
positions, account snapshots, and a system-events audit log. Every
historical read requires an `as_of: datetime` and filters
`available_at <= as_of`, so a backtest or training query can never see
data that was not yet available at that point in time. `app/ingest`
pulls from `app.toss` (market data) and mock news/DART collectors and
writes through those repositories, idempotently. See
`docs/architecture/0008-data-platform.md` (ERD, idempotency rules,
point-in-time design) and `docs/architecture/0009-corporate-actions-and-adjusted-price.md`
(documented future extensions).

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
research    -> core                 (Phase 01, see ADR 0006)
toss        -> core, adapters       (Phase 02, see ADR 0007)
db          -> core                                  (Phase 03, see ADR 0008)
ingest      -> core, db, toss, data, research         (Phase 03, see ADR 0008)
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
| `app/research` | Strategy Research Lab: `StrategySpec` model, file-based Strategy Registry, isolated TradingView MCP health check |
| `app/toss` | Toss Open API integration: OAuth2 client, `MarketDataAdapter`, `PortfolioReadAdapter` - read-only, no order-placing code |
| `app/db` | Data Platform: PostgreSQL schema (`schema.py`), migrations (`alembic/`), repositories with point-in-time (`as_of`) reads and idempotent upserts, data quality metrics |
| `app/ingest` | Ingestion orchestration: pulls from `app.toss`/collector interfaces and writes through `app.db.repositories`; news/DART mock collectors, market-bar ingestor, Strategy Registry DB sync, interval scheduler |

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
- `0006-strategy-research-lab.md` - `StrategySpec`, the status ladder,
  and why TradingView MCP is isolated from the rest of the system
- `0007-toss-api-integration.md` - the confirmed Toss Open API spec
  used, raw-vs-normalized model split, error mapping, rate limiting,
  and the code-level read-only enforcement
- `0008-data-platform.md` - ERD, the three column conventions,
  idempotency rules, and the point-in-time (`as_of`) read guarantee
- `0009-corporate-actions-and-adjusted-price.md` - documented future
  extensions (adjusted price, full bi-temporal history, a trading
  calendar) - a design record only, nothing implemented yet

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

## PostgreSQL and migrations (Phase 03)

```bash
docker compose up -d db      # starts a local Postgres matching .env.example
alembic upgrade head          # creates all 15 tables
alembic downgrade base         # drops them again (round-trips cleanly - see ADR 0008)
```

`DATABASE_URL` in `.env` (see `.env.example`) is the only place a
connection string is configured - `alembic/env.py` and
`app.db.engine.build_engine` both read it from `Settings`, never a
hardcoded value.

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
- `app/toss` (Phase 02) never places, modifies, or cancels an order:
  `TossRestClient` exposes only `get()`, and construction fails
  immediately unless `Settings.toss_read_only_mode` (default `true`)
  is set - see ADR 0007. `TOSS_CLIENT_ID`/`TOSS_CLIENT_SECRET`/
  `TOSS_ACCOUNT_SEQ` are never hardcoded or logged (`pydantic.SecretStr`
  end to end; see `tests/toss/test_secret_redaction.py`).
- `app/db` (Phase 03) has no "get everything" read method for
  historical data - every such method requires `as_of` and filters
  `available_at <= as_of`, so a model-training or backtest query can
  never see future-relative-to-`as_of` data. Every ingestible table
  has a natural-key uniqueness constraint, so re-ingesting the same
  event twice never creates a duplicate row - see ADR 0008.

## Strategy Research Lab (Phase 01)

TradingView + Claude MCP are used only to research strategies, never
to run one live. See:
- `docs/research/strategy-research-lab-guide.md` - how to create,
  save, and reload a `StrategySpec`
- `docs/research/tradingview-mcp-health-check.md` - manual procedure
  for checking TradingView MCP connectivity (never a prerequisite for
  `make test` or anything else in this repo)
- `research/strategies/STR-EXT-001/0.1.0.json` - a sample external
  strategy idea, registered at `status=research` only

## Toss Open API integration (Phase 02)

Read-only. See:
- `docs/architecture/0007-toss-api-integration.md` - what was
  confirmed against the official docs vs. inferred, and why
- `app/toss/factory.py::build_toss_gateways(settings)` - wires
  `Settings` into a `MarketDataAdapter`/`PortfolioReadAdapter` pair
- `tests/toss/test_integration_live.py` - the opt-in (real-credential)
  integration test, skipped by default and in this environment always
  skipped (network access to `*.tossinvest.com` is blocked here - see
  ADR 0007)

```python
from app.core.config import get_settings
from app.toss.factory import build_toss_gateways

gateways = build_toss_gateways(get_settings())
quote = gateways.market_data.get_price("005930")
```

## Data Platform (Phase 03)

Every historical read requires `as_of` and filters `available_at <=
as_of` - see `docs/architecture/0008-data-platform.md`.

```python
from datetime import UTC, datetime

from app.db.engine import build_engine, build_session_factory, session_scope
from app.db.repositories import InstrumentRepository, MarketBarRepository
from app.core.config import get_settings

engine = build_engine(get_settings())
with session_scope(build_session_factory(engine)) as session:
    instrument = InstrumentRepository(session).get_or_create(
        exchange="KRX", symbol="005930", source="toss_openapi"
    )
    bars = MarketBarRepository(session).get_bars_as_of(
        instrument_id=instrument.id,
        timeframe="1d",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 3, 1, tzinfo=UTC),
        as_of=datetime.now(UTC),  # never see bars that weren't available yet
    )
```

## Roadmap

- **Phase 00 (done)**: project skeleton - config, logging, exceptions,
  HTTP timeout/retry policy, module interfaces, tests, tooling.
- **Phase 01 (done)**: Strategy Research Lab - `StrategySpec`, file-
  based Strategy Registry, isolated TradingView MCP health check.
- **Phase 02 (done)**: Toss Open API integration - OAuth2 auth,
  Market Data Gateway, Portfolio Read Gateway, all read-only.
- **Phase 03 (done)**: Data Platform - PostgreSQL schema + migrations,
  point-in-time repositories, idempotent ingestion, data quality
  metrics, news/DART mock collectors.
- **Phase 04+**: a first Scanner (reading through `app.db.repositories`
  exclusively), a first backtest engine implementation, a paper broker
  implementation, and confirming the remaining 9 Toss endpoints'
  response schemas - each phase should only need to fill in a
  `base.py` interface (or add a DTO/table), not change these
  boundaries.
