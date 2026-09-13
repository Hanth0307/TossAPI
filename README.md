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
data that was not yet available at that point in time - and for the
tables where an external source can issue a correction
(`market_bars`, `news_events`, `disclosure_events`), a correction is
appended as a new revision rather than overwriting history, so
re-running a query at an `as_of` before the correction still returns
the original value (see `tests/db/test_point_in_time_correction.py`).
`app/ingest` pulls from `app.toss` (market data) and mock news/DART
collectors and writes through those repositories, idempotently. See
`docs/architecture/0008-data-platform.md` (ERD, idempotency rules,
point-in-time design) and
`docs/architecture/0009-corporate-actions-and-adjusted-price.md`
(the correction-history fix, plus still-deferred adjusted-price/
corporate-action/trading-calendar extensions).

**Phase 04: Scanner layer.** `app/scanners` narrows "every known
instrument" down to research candidates in four stages - Market
(`InstrumentRepository.list_all`) -> Universe Filter
(liquidity/turnover/price-range/status, thresholds always passed in,
never hardcoded) -> Event Scanner (price gap, abnormal volume,
volatility spike, news/disclosure occurrence, orderbook imbalance -
existence/count-based only, no invented sentiment score - with a
`market` field so Korean/US-specific rules stay separate) -> Strategy
Scanner (evaluates a structured `StrategyRuleSet`, deliberately
separate from `StrategySpec`'s free-text research prose, against a
computed `FeatureSet`). The output is a `Candidate` per instrument
carrying every stage's PASS/FAIL and observed values, never a bare
ticker list and never an order - `app.brokers`/`app.execution` remain
interface-only regardless of a `Candidate.qualified` flag.
`ScannerPipeline` reads exclusively through `app.db.repositories`'s
`as_of`-gated methods, so a scan is exactly as leak-free as the data
platform underneath it (see
`tests/scanners/test_pipeline_integration.py`). See
`docs/architecture/0010-scanner-pipeline.md`.

**Phase 05: AI Context, Quant Model, Market Regime, Signal Engine.**
Four packages, deliberately kept apart until `app.signals`: `app/
ai_context` turns one news/disclosure item into a fixed structured
classification via `client.messages.parse` (entity links, event type,
direct/indirect and one-off/structural impact, novelty/dedup
clustering, source reliability, a 1d/5d/10d/long-term impact horizon)
- an LLM failure or an unparseable response becomes an explicit
`status=unknown` result with every field at its `UNKNOWN` variant,
never a guess. `app/regime` classifies trend/volatility/breadth from
`as_of`-gated benchmark bars, every threshold passed in explicitly.
`app/models` trains a baseline (logistic regression + calibration)
quant model on a 5-trading-day forward-return label, with feature and
label windows fetched from two structurally separate repository calls
so leakage is prevented by the code shape, not a convention; evaluation
reports AUC, precision/recall, Brier score, Expected Calibration
Error, class balance, and per-period/per-regime breakdowns together,
never AUC alone. `app/signals` combines all three into a `SignalInput`
per `(instrument, as_of)` - **still no order is generated anywhere in
this phase**. See
`docs/architecture/0011-ai-context-quant-regime-signal-engine.md`.

## Module map and dependency direction

```
core        <- (everything; core imports nothing else under app/)
adapters    -> core
data        -> core, adapters
strategies  -> core, data, models
backtest    -> core, data, strategies
brokers     -> core, adapters
risk        -> core, brokers        (OrderRequest type only)
execution   -> core, brokers, risk
research    -> core                                   (Phase 01, see ADR 0006)
toss        -> core, adapters                         (Phase 02, see ADR 0007)
db          -> core                                  (Phase 03, see ADR 0008)
ingest      -> core, db, toss, data, research         (Phase 03, see ADR 0008)
scanners    -> core, db                               (Phase 04, see ADR 0010)
models      -> core, db                               (Phase 05, see ADR 0011)
ai_context  -> core, db                               (Phase 05, see ADR 0011)
regime      -> core, db                               (Phase 05, see ADR 0011)
signals     -> core, db, ai_context, models, regime   (Phase 05, see ADR 0011)
```

| Package | Responsibility |
|---|---|
| `app/core` | Settings (`config.py`), structured logging (`logging.py`), exception hierarchy (`exceptions.py`) |
| `app/adapters` | Common outbound-HTTP timeout/retry policy (`http_client.py`) |
| `app/data` | Market data / news / disclosure provider interfaces |
| `app/strategies` | Strategy interface (market data + signals -> order intents) |
| `app/backtest` | Backtest engine interface |
| `app/brokers` | Broker adapter interface (paper/live) - no real order calls |
| `app/risk` | Risk engine interface - gates every order before a broker sees it |
| `app/execution` | Orchestrates risk check + broker submission for one order |
| `app/research` | Strategy Research Lab: `StrategySpec` model, file-based Strategy Registry, isolated TradingView MCP health check |
| `app/toss` | Toss Open API integration: OAuth2 client, `MarketDataAdapter`, `PortfolioReadAdapter` - read-only, no order-placing code |
| `app/db` | Data Platform: PostgreSQL schema (`schema.py`), migrations (`alembic/`), repositories with point-in-time (`as_of`) reads and idempotent upserts, data quality metrics |
| `app/ingest` | Ingestion orchestration: pulls from `app.toss`/collector interfaces and writes through `app.db.repositories`; news/DART mock collectors, market-bar ingestor, Strategy Registry DB sync, interval scheduler |
| `app/scanners` | Scanner pipeline: Market -> Universe Filter -> Event Scanner -> Strategy Scanner -> `Candidate`, reading exclusively through `app.db.repositories` |
| `app/models` | Quant Model: baseline logistic-regression-plus-calibration `SignalModel`, leakage-safe feature/label/dataset construction, time-ordered training, evaluation, artifact storage |
| `app/ai_context` | LLM-based news/disclosure classification: fixed output schema, isolated Claude API call with explicit `unknown` fallback |
| `app/regime` | Market Regime: trend/volatility/breadth classification from `as_of`-gated benchmark bars |
| `app/signals` | Signal Engine: structures AI Context + Quant probability + Regime into `SignalInput` - never an order |

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
- `0008-data-platform.md` - ERD, the four column conventions,
  idempotency rules, and the point-in-time (`as_of`) read guarantee
- `0009-corporate-actions-and-adjusted-price.md` - **implemented**:
  append-only revision history for `market_bars`/`news_events`/
  `disclosure_events`, why in-place correction was a real point-in-
  time leak, not an acceptable simplification. Also documents
  adjusted price, corporate actions, and a trading calendar as
  still-deferred design records
- `0010-scanner-pipeline.md` - the Market -> Universe Filter -> Event
  Scanner -> Strategy Scanner -> `Candidate` pipeline, why
  `StrategyRuleSet` is separate from `StrategySpec` prose, the
  market-specific event-rule mechanism, and the interfaces Phase 05
  is expected to consume (`FeatureSet`, `EventDetection`, `Candidate`)
- `0011-ai-context-quant-regime-signal-engine.md` - the fixed AI
  Context schema and its isolated/unknown-fallback LLM call, the Quant
  Model's label/feature/leakage-prevention design and calibration
  evaluation, the Market Regime classifier, and the `SignalInput`
  structure `app.signals` produces (never an order)

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
alembic upgrade head          # creates all 16 tables
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
  event twice never creates a duplicate row - see ADR 0008. For
  `market_bars`/`news_events`/`disclosure_events`, a correction is
  appended as a new revision rather than overwriting history, so this
  guarantee holds even after a correction lands - see ADR 0009.
- `app/scanners` (Phase 04) never places, suggests, or triggers a
  trade - a `Candidate.qualified=True` is a research artifact, not an
  order, and `app/brokers`/`app/execution` stay interface-only
  regardless of it. No sentiment/quality score is invented for news or
  disclosure events - `NewsOccurrenceEventScanner`/
  `DisclosureOccurrenceEventScanner` are existence/count-based only.
  Every filter/event threshold is a required constructor argument;
  none is hardcoded in scanner logic - see ADR 0010.
- `app/ai_context` (Phase 05) never fabricates a value: an LLM call
  failure or an unparseable response produces an `AIContextResult`
  with `status=unknown` and every classification field at its explicit
  `UNKNOWN` variant, never a raised exception into a caller and never
  a guessed value. `app/models` (Phase 05) fetches a training sample's
  features and label from two structurally separate `as_of`-gated
  repository calls, so the label horizon cannot leak into the feature
  vector - see ADR 0011. `app/signals` (Phase 05) never generates an
  order either - the same guarantee as `app/scanners`.

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

## Scanner pipeline (Phase 04)

`Candidate`s are research artifacts, never orders - see
`docs/architecture/0010-scanner-pipeline.md`.

```python
from datetime import UTC, datetime
from decimal import Decimal

from app.core.config import get_settings
from app.db.engine import build_engine, build_session_factory, session_scope
from app.scanners.events import AbnormalVolumeEventScanner
from app.scanners.pipeline import PipelineConfig, ScannerPipeline
from app.scanners.universe import LiquidityFilter

engine = build_engine(get_settings())
with session_scope(build_session_factory(engine)) as session:
    pipeline = ScannerPipeline(
        session,
        config=PipelineConfig(
            timeframe="1d",
            lookback_days=20,
            news_lookback_days=7,
            disclosure_lookback_days=30,
            exchange="KRX",
        ),
        universe_filters=[LiquidityFilter(min_turnover_value=Decimal("1000000000"))],
        event_scanners=[
            AbnormalVolumeEventScanner(min_volume_multiple=Decimal("3"), market="KRX")
        ],
        strategy_rule_set=None,
        data_source="toss_openapi",
    )
    candidates = pipeline.scan(as_of=datetime.now(UTC))
    qualified = [c for c in candidates if c.qualified]
```

## AI Context, Quant Model, Regime, Signal Engine (Phase 05)

A `SignalInput` is evidence, never an order - see
`docs/architecture/0011-ai-context-quant-regime-signal-engine.md`.

```python
from datetime import UTC, datetime
from decimal import Decimal

from app.ai_context.claude_extractor import ClaudeContextExtractor
from app.ai_context.extractor import ContextExtractionRequest
from app.ai_context.schema import EventKind
from app.core.config import get_settings
from app.db.engine import build_engine, build_session_factory, session_scope
from app.regime.classifier import RegimeClassifier
from app.regime.provider import RegimeProvider
from app.signals.engine import SignalEngine

settings = get_settings()

# AI Context: any LLM failure/parse failure becomes an explicit
# `status="unknown"` result - never a guess, never a raised exception.
extractor = ClaudeContextExtractor(
    api_key=settings.anthropic_api_key.get_secret_value(),
    model=settings.anthropic_model,
)
context_result = extractor.extract(
    ContextExtractionRequest(
        source="mock_news", external_id="n-1", event_kind=EventKind.NEWS,
        event_time=datetime.now(UTC), headline_or_title="Samsung Q3 earnings beat",
        body="...",
    )
)

engine = build_engine(settings)
with session_scope(build_session_factory(engine)) as session:
    regime_provider = RegimeProvider(
        session,
        classifier=RegimeClassifier(
            trend_lookback_bars=20,
            trend_up_threshold=Decimal("0.03"),
            trend_down_threshold=Decimal("-0.03"),
            volatility_lookback_bars=20,
            high_volatility_threshold=Decimal("0.02"),
            low_volatility_threshold=Decimal("0.001"),
            breadth_expanding_threshold=Decimal("0.6"),
            breadth_contracting_threshold=Decimal("0.4"),
        ),
        benchmark_instrument_id=1, timeframe="1d", lookback_days=30,
    )
    signal_engine = SignalEngine(
        session, regime_provider=regime_provider,
        quant_model=None,  # or a loaded BaselineQuantModel (app.models.artifact.load_artifact)
        quant_model_name="quant_baseline", quant_model_version="logreg_v1",
        quant_feature_schema_version="1.0.0", quant_label_definition_version="fwd_return_5d_v1",
        feature_timeframe="1d", feature_lookback_days=30,
    )
    signal = signal_engine.build_signal_input(
        instrument_id=1, symbol="005930", as_of=datetime.now(UTC),
        ai_context=[context_result],
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
- **Phase 04 (done)**: Scanner layer - Market -> Universe Filter ->
  Event Scanner -> Strategy Scanner -> `Candidate`, reading through
  `app.db.repositories` exclusively, market-specific event rules,
  `FeatureSet`/`EventDetection`/`Candidate` interfaces for Phase 05.
- **Phase 05 (done)**: AI Context (`app.ai_context`), Quant Model
  (`app.models`), Market Regime (`app.regime`), and the Signal Engine
  (`app.signals`) - a baseline calibrated quant model on a leakage-safe
  dataset, a fixed/isolated LLM classification schema, and a
  `SignalInput` combining all three, still no order generated.
- **Phase 06+**: a first backtest engine implementation (consuming
  `app.signals.schema.SignalInput` and/or `app.scanners.candidate.
  Candidate`), a paper broker implementation, and confirming the
  remaining 9 Toss endpoints' response schemas - each phase should
  only need to fill in a `base.py` interface (or add a DTO/table), not
  change these boundaries.
