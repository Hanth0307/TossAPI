"""PostgreSQL schema (SQLAlchemy Core) for the Phase 03 Data Platform.

Every table follows one of four column conventions, documented in
docs/architecture/0008-data-platform.md:

- **Revisioned observed-event tables** (market_bars, news_events,
  disclosure_events): `event_time`/`available_at`/`ingested_at` as
  below, plus `revision` (an integer, monotonically increasing per
  logical event). The natural-key `UniqueConstraint` includes
  `available_at`, so a correction (a new `available_at` for the same
  logical event) INSERTs a new revision row instead of overwriting the
  old one - see `app.db.upsert.append_revision_rows` and ADR 0009 for
  why plain "UPDATE in place, keep the original available_at" leaks
  future-corrected values into a point-in-time read whose `as_of`
  predates the correction. Re-submitting the exact same correction
  (identical `available_at`) is still idempotent (`ON CONFLICT DO
  UPDATE` touching only `ingested_at`).
- **Plain observed-event tables** (trade_ticks, orderbook_snapshots,
  signals, positions, account_snapshots, ai_context_annotations):
  `event_time` (when it
  happened), `available_at` (when *we* could first have known it -
  the point-in-time cutoff every historical read filters on; see
  `app.db.repositories`), `ingested_at` (last time this row was
  written/touched). A natural-key `UniqueConstraint` (NOT including
  `available_at`) makes re-ingesting the same event idempotent via
  `app.db.upsert.upsert_event_rows` (`ON CONFLICT DO UPDATE`,
  `available_at` excluded from the `SET` clause so it is preserved
  from first insert). These are not expected to be externally
  corrected in the way news/disclosures/market prices are - see ADR
  0009 for the scope decision and how to extend the revisioned
  pattern to one of these later if that changes.
- **Operational run tables** (model_runs, backtest_runs): our own
  pipeline executions, not observed market data - `started_at`/
  `finished_at`/`status` plus a nullable-but-unique `idempotency_key`
  so retrying/resuming a run after a restart never creates a duplicate.
- **Order tables** (paper_orders, broker_orders): our own actions:
  unique on `client_order_id` (mirroring `app.brokers.base.OrderRequest`
  from Phase 00), so a retried submission can never be recorded twice.

Every raw-response-shaped column is nullable `JSONB` (`raw_payload` or
similar) - normalized columns are only added once a real field-level
schema is confirmed (see ADR 0007's `UnparsedRecord` precedent for
`account_snapshots` in particular, whose Toss field names are still
unconfirmed per that ADR).
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TIMESTAMP

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _id() -> Column:
    return Column("id", BigInteger, Identity(always=True), primary_key=True)


def _event_columns() -> list[Column]:
    """event_time / available_at / ingested_at - see module docstring."""
    return [
        Column("event_time", TIMESTAMP(timezone=True), nullable=False),
        Column("available_at", TIMESTAMP(timezone=True), nullable=False),
        Column(
            "ingested_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=text("now()"),
        ),
    ]


def _revision_column() -> Column:
    """Monotonically increasing per logical event - see
    `app.db.upsert.append_revision_rows`. Not a server-generated
    sequence: computed per-insert from existing rows sharing the same
    logical key, so it starts at 1 for every distinct event.
    """
    return Column("revision", Integer, nullable=False)


# --- Reference data -------------------------------------------------------

instruments = Table(
    "instruments",
    metadata,
    _id(),
    Column("exchange", String(32), nullable=False),
    Column("symbol", String(32), nullable=False),
    Column("name", Text, nullable=True),
    Column("currency", String(8), nullable=True),
    Column("source", String(32), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("raw_payload", JSONB, nullable=True),
    UniqueConstraint("exchange", "symbol"),
)

# --- Market data (observed-event) -----------------------------------------

market_bars = Table(
    "market_bars",
    metadata,
    _id(),
    Column(
        "instrument_id",
        BigInteger,
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("timeframe", String(8), nullable=False),
    *_event_columns(),
    _revision_column(),
    Column("open_price", Numeric, nullable=False),
    Column("high_price", Numeric, nullable=False),
    Column("low_price", Numeric, nullable=False),
    Column("close_price", Numeric, nullable=False),
    Column("volume", Numeric, nullable=False),
    Column("currency", String(8), nullable=True),
    Column("source", String(32), nullable=False),
    Column("raw_payload", JSONB, nullable=True),
    # available_at is part of the natural key on purpose - a correction
    # (new available_at) is a new revision row, never an overwrite of
    # the original. See module docstring and ADR 0009.
    UniqueConstraint("instrument_id", "timeframe", "event_time", "source", "available_at"),
    Index("ix_market_bars_lookup", "instrument_id", "timeframe", "event_time"),
)

trade_ticks = Table(
    "trade_ticks",
    metadata,
    _id(),
    Column(
        "instrument_id",
        BigInteger,
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    ),
    *_event_columns(),
    Column("price", Numeric, nullable=False),
    Column("volume", Numeric, nullable=False),
    Column("currency", String(8), nullable=True),
    Column("source", String(32), nullable=False),
    Column("raw_payload", JSONB, nullable=True),
    # No trade id is confirmed in the Toss trade DTO (ADR 0007), so the
    # natural key is the full observed tuple - two genuinely distinct
    # trades with identical timestamp+price+volume are indistinguishable
    # and the second is dropped. Documented limitation, not a bug.
    UniqueConstraint("instrument_id", "event_time", "source", "price", "volume"),
    Index("ix_trade_ticks_lookup", "instrument_id", "event_time"),
)

orderbook_snapshots = Table(
    "orderbook_snapshots",
    metadata,
    _id(),
    Column(
        "instrument_id",
        BigInteger,
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    ),
    *_event_columns(),
    Column("currency", String(8), nullable=True),
    Column("asks", JSONB, nullable=False),
    Column("bids", JSONB, nullable=False),
    Column("source", String(32), nullable=False),
    Column("raw_payload", JSONB, nullable=True),
    UniqueConstraint("instrument_id", "event_time", "source"),
    Index("ix_orderbook_snapshots_lookup", "instrument_id", "event_time"),
)

# --- News / disclosures (observed-event) ----------------------------------

news_events = Table(
    "news_events",
    metadata,
    _id(),
    Column("source", String(32), nullable=False),
    Column("external_id", String(128), nullable=False),
    *_event_columns(),
    _revision_column(),
    Column("headline", Text, nullable=False),
    Column("body", Text, nullable=True),
    Column("related_symbols", JSONB, nullable=True),
    Column("raw_payload", JSONB, nullable=True),
    # available_at part of the natural key - see market_bars above / ADR 0009.
    UniqueConstraint("source", "external_id", "available_at"),
)

disclosure_events = Table(
    "disclosure_events",
    metadata,
    _id(),
    Column("source", String(32), nullable=False),
    Column("external_id", String(128), nullable=False),
    Column(
        "instrument_id",
        BigInteger,
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
    ),
    *_event_columns(),
    _revision_column(),
    Column("title", Text, nullable=False),
    Column("filing_type", String(64), nullable=True),
    Column("raw_payload", JSONB, nullable=True),
    # available_at part of the natural key - see market_bars above / ADR 0009.
    UniqueConstraint("source", "external_id", "available_at"),
)

# --- AI Context annotations (Phase 05, observed-event) --------------------

ai_context_annotations = Table(
    "ai_context_annotations",
    metadata,
    _id(),
    Column("source", String(32), nullable=False),
    Column("external_id", String(128), nullable=False),
    Column("event_kind", String(16), nullable=False),
    Column("model_name", String(64), nullable=False),
    Column("model_version", String(64), nullable=False),
    *_event_columns(),
    Column("status", String(16), nullable=False),
    Column("event_type", String(32), nullable=False),
    Column("impact_direction", String(16), nullable=False),
    Column("impact_duration", String(16), nullable=False),
    Column("novelty", String(16), nullable=False),
    Column("duplicate_cluster_id", String(128), nullable=True),
    Column("source_reliability", String(16), nullable=False),
    Column("impact_horizon", JSONB, nullable=False),
    Column("entities", JSONB, nullable=False),
    Column("summary", Text, nullable=False),
    Column("rationale", Text, nullable=False),
    Column("parse_error", Text, nullable=True),
    # A re-run of the exact same model_version against the same
    # article is idempotent (plain upsert) - this is a derived
    # annotation recomputed from immutable source text, not an
    # externally correctable fact, so the append-only revision
    # pattern (ADR 0009) would be needless complexity here. A
    # different model_version is a different row entirely - see ADR
    # 0011.
    UniqueConstraint("source", "external_id", "event_kind", "model_name", "model_version"),
    Index("ix_ai_context_annotations_lookup", "source", "external_id", "event_kind"),
)

# --- Strategy Research Lab mirror (dimension table) -----------------------

strategy_registry = Table(
    "strategy_registry",
    metadata,
    _id(),
    Column("strategy_id", String(64), nullable=False),
    Column("version", String(32), nullable=False),
    Column("name", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("source", String(32), nullable=False),
    Column("spec_created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("synced_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("spec_json", JSONB, nullable=False),
    UniqueConstraint("strategy_id", "version"),
)

# --- Signals / runs --------------------------------------------------------

model_runs = Table(
    "model_runs",
    metadata,
    _id(),
    Column("model_name", String(128), nullable=False),
    Column("model_version", String(32), nullable=True),
    Column("strategy_id", String(64), nullable=True),
    Column("strategy_version", String(32), nullable=True),
    Column("status", String(16), nullable=False),
    Column("idempotency_key", String(128), nullable=True),
    Column("started_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
    Column("params", JSONB, nullable=True),
    Column("metrics", JSONB, nullable=True),
    UniqueConstraint("idempotency_key"),
)

signals = Table(
    "signals",
    metadata,
    _id(),
    Column(
        "model_run_id",
        BigInteger,
        ForeignKey("model_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "instrument_id",
        BigInteger,
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    ),
    *_event_columns(),
    Column("signal_value", Numeric, nullable=True),
    Column("signal_label", String(32), nullable=True),
    Column("payload", JSONB, nullable=True),
    Column("source", String(32), nullable=False),
    UniqueConstraint("model_run_id", "instrument_id", "event_time"),
)

backtest_runs = Table(
    "backtest_runs",
    metadata,
    _id(),
    Column("strategy_id", String(64), nullable=False),
    Column("strategy_version", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column("idempotency_key", String(128), nullable=True),
    Column("period_start", TIMESTAMP(timezone=True), nullable=False),
    Column("period_end", TIMESTAMP(timezone=True), nullable=False),
    Column("started_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
    Column("params", JSONB, nullable=True),
    Column("metrics", JSONB, nullable=True),
    UniqueConstraint("idempotency_key"),
)

# --- Orders (our own actions - no order-mutating code calls these from
# app.toss/app.brokers in this phase; they exist so a future paper/live
# broker has somewhere to record what it did) ------------------------------

paper_orders = Table(
    "paper_orders",
    metadata,
    _id(),
    Column("client_order_id", String(128), nullable=False),
    Column(
        "instrument_id",
        BigInteger,
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("side", String(8), nullable=False),
    Column("order_type", String(16), nullable=False),
    Column("quantity", Numeric, nullable=False),
    Column("limit_price", Numeric, nullable=True),
    Column("status", String(16), nullable=False),
    Column("submitted_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("raw_payload", JSONB, nullable=True),
    UniqueConstraint("client_order_id"),
)

broker_orders = Table(
    "broker_orders",
    metadata,
    _id(),
    Column("broker_order_id", String(128), nullable=False),
    Column("client_order_id", String(128), nullable=True),
    Column("source", String(32), nullable=False),
    Column(
        "instrument_id",
        BigInteger,
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("side", String(8), nullable=True),
    Column("order_type", String(16), nullable=True),
    Column("quantity", Numeric, nullable=True),
    Column("limit_price", Numeric, nullable=True),
    Column("status", String(16), nullable=False),
    Column("submitted_at", TIMESTAMP(timezone=True), nullable=True),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("raw_payload", JSONB, nullable=True),
    UniqueConstraint("broker_order_id", "source"),
)

# --- Portfolio state (observed-event) -------------------------------------

positions = Table(
    "positions",
    metadata,
    _id(),
    Column("account_id", String(64), nullable=False),
    Column(
        "instrument_id",
        BigInteger,
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    ),
    *_event_columns(),
    Column("quantity", Numeric, nullable=False),
    Column("avg_price", Numeric, nullable=True),
    Column("source", String(32), nullable=False),
    Column("raw_payload", JSONB, nullable=True),
    UniqueConstraint("account_id", "instrument_id", "event_time", "source"),
    Index("ix_positions_lookup", "account_id", "instrument_id", "event_time"),
)

account_snapshots = Table(
    "account_snapshots",
    metadata,
    _id(),
    Column("account_id", String(64), nullable=False),
    *_event_columns(),
    # Nullable/normalized-when-known: Toss's account/balance response
    # field names are unconfirmed (ADR 0007) - raw_payload is the
    # primary content until they are.
    Column("cash_balance", Numeric, nullable=True),
    Column("buying_power", Numeric, nullable=True),
    Column("source", String(32), nullable=False),
    Column("raw_payload", JSONB, nullable=True),
    UniqueConstraint("account_id", "event_time", "source"),
)

# --- Operational audit log -------------------------------------------------

system_events = Table(
    "system_events",
    metadata,
    _id(),
    Column("event_type", String(64), nullable=False),
    Column("source", String(32), nullable=False),
    Column("severity", String(16), nullable=False),
    Column("message", Text, nullable=False),
    Column("details", JSONB, nullable=True),
    Column("occurred_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("ingested_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("dedup_key", String(128), nullable=True),
    UniqueConstraint("dedup_key"),
    Index("ix_system_events_lookup", "event_type", "occurred_at"),
)
