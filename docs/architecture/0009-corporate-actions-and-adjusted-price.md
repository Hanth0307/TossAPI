# ADR 0009: Correction history (implemented), corporate actions and adjusted price (still deferred)

## Status
Accepted (Phase 03); **amended (Phase 03 review)** - the original
version of this ADR treated "a correction overwrites the row in
place, keeping the original `available_at`" as an acceptable
simplification. It is not: it is a point-in-time information leak,
explained below, and has been fixed. The corporate-actions/adjusted-
price and trading-calendar sections remain design records only -
nothing there is implemented.

## Context

### Why the original "documented simplification" was actually a bug
ADR 0008's original write path (`app.db.upsert.upsert_event_rows`) did
`INSERT ... ON CONFLICT (natural key) DO UPDATE SET <value columns>`,
deliberately excluding `available_at` from the `SET` clause so it
stayed pinned to the row's first-seen time. That was framed as "a
point-in-time query keeps returning a stable answer for a given
`as_of`" - true for the case of "does this event exist yet", false for
"what value did it have". Concretely:

```
Original:   value=100, available_at=2026-09-01
Correction: value=105, available_at=2026-09-03
```

Under in-place UPDATE, after the correction lands there is **one row**
with `value=105` and `available_at=2026-09-01` (preserved). A query
with `as_of=2026-09-02` - a date that, at the time, had only ever seen
`value=100` - now returns `105`. That is not a stale-data problem, it
is **future information leaking into the past**: a backtest or a
model-training run pinned to `as_of=2026-09-02`, re-executed after the
correction ingests, silently produces a different result than it did
(and than it legitimately could have) on 2026-09-02 itself. For a
platform whose entire purpose is point-in-time-correct simulation,
that is the one failure mode the `as_of` parameter exists to prevent -
so this is a correctness bug in the storage layer, not a documented
tradeoff, and letting it stand until "some future phase" would mean
every model/backtest result produced from `market_bars`/`news_events`/
`disclosure_events` before the fix carries an unstated risk of having
been computed on leaked data.

## Decision

### Implemented now: append-only revision history for correctable data
`market_bars`, `news_events`, and `disclosure_events` - the tables
whose values can legitimately be corrected by an external source
(a restated print, an amended/corrected article or filing) - moved
from "one current row per natural key" to "append a new revision row
per correction, never overwrite":

- Each of these tables gained an integer `revision` column and its
  natural-key `UniqueConstraint` now includes `available_at`
  (`app/db/schema.py`; migration
  `alembic/versions/0002_revision_history_for_correctable_events.py`).
  A correction (a new `available_at` for the same logical event) is
  therefore a new row, not a conflict target for the original one.
- `app.db.upsert.append_revision_rows` computes `revision` as `1 +
  max(existing revisions for this logical key)` and inserts. Re-
  submitting the exact same correction (identical `available_at`) is
  still idempotent - `ON CONFLICT (logical key, available_at) DO
  UPDATE SET ingested_at = EXCLUDED.ingested_at` touches nothing else.
- `app.db.repositories._revisions.select_latest_revision_as_of` reads
  the correct value for a given `as_of`: per logical event, the
  revision with the greatest `available_at <= as_of` (`SELECT DISTINCT
  ON`, ordered `available_at DESC, revision DESC`, wrapped and
  re-sorted by `event_time` for the caller). A revision whose
  `available_at` is after the query's `as_of` is excluded from the
  candidate set entirely - not merely outranked - so it structurally
  cannot be selected.
- `MarketBarRepository.upsert_bars`, `NewsRepository.upsert_news`, and
  `DisclosureRepository.upsert_disclosures` all route through this
  path now; their `get_*_as_of` signatures are unchanged, only their
  correctness under correction is.

With this in place, the example above resolves correctly:
`as_of=2026-09-02` returns `100` (the `available_at=2026-09-03` row is
excluded by the filter), `as_of=2026-09-04` returns `105`. See
`tests/db/test_point_in_time_correction.py` for the full regression
suite covering this exact scenario plus idempotent resubmission and
the "ingesting a correction never changes a past `as_of` result"
property directly.

### Deliberately out of scope for this fix
`trade_ticks`, `orderbook_snapshots`, `signals`, `positions`, and
`account_snapshots` keep the original in-place-update behavior
(`app.db.upsert.upsert_event_rows`, `available_at` preserved from first
insert). These are not, today, externally correctable in the sense
market prices/news/disclosures are - a tick or a snapshot is a
one-time observation, and our own signals/positions/account state are
recomputed per run rather than "corrected" by a third party. If that
changes for any of them, extending the same `revision`-column +
`available_at`-in-the-key pattern to that table is the same mechanical
change made here - not a redesign. `instruments` (reference/master
data such as a company's display name) is likewise left as a plain
mutable dimension row: nothing in this codebase reads instrument
attributes as a point-in-time-sensitive backtest input today, so
revisioning it would be complexity with no corresponding correctness
gain - "정정 가능한 observed event"에 해당하지 않는 순수 참조 데이터로 간주함
(not treated as a correctable observed event, since it is pure
reference data). This can be revisited if a concrete need for "what
was this instrument's name as of date X" appears.

### Still deferred: corporate actions / adjusted price
`market_bars` stores raw OHLCV as reported - unaffected by this
change. A stock split, dividend, or other corporate action changes
what a historical price *means* relative to the current share
count/price basis; a backtest spanning such an event needs an
adjusted series, but adjustment is a derived view, not a fact about
what printed. Future work (not implemented here): a
`corporate_actions` table (`instrument_id`, `action_type`,
`event_time` as ex-date, `available_at`/`ingested_at`, a `details`
JSONB column until a real source's field names are confirmed,
following the `UnparsedRecord`/ADR 0007 discipline), with adjustment
computed at **read time** (e.g. a future
`get_adjusted_bars_as_of(...)`) by folding `corporate_actions` rows
into an adjustment factor - never by mutating `market_bars` rows,
for the same reason corrections are no longer mutated in place: an
adjustment methodology that turns out to be wrong must be fixable
without rewriting history.

### Still deferred: trading calendar
`app.db.quality.compute_market_data_quality` estimates missing bars
from a fixed interval, which over-counts "missing" for calendar-gapped
timeframes (daily bars skip weekends/holidays). A future
`trading_calendar` reference table (`exchange`, `date`,
`is_trading_day`) would let it compute `expected_bar_count` from
actual trading days instead.

## Consequences
- The point-in-time leak described above is closed for `market_bars`,
  `news_events`, and `disclosure_events` - the three tables where an
  external correction is a realistic occurrence. Every existing test
  in `tests/db/` and `tests/ingest/` that exercised the old in-place
  behavior for these tables was updated (not merely left passing by
  coincidence) to assert the new append-only behavior; the full 204-
  test Phase 03 suite plus the new regression tests pass together.
- `revision` is computed with a `SELECT MAX(...)` per row inside
  `append_revision_rows`, run one row at a time per call rather than
  as a single bulk statement, specifically so two corrections for the
  same event submitted together get correctly ordered, distinct
  revision numbers. This assumes a single writer per logical event
  within one ingestion call, which holds for every caller in this
  codebase today (no concurrent ingestion pipelines exist yet) -
  documented here rather than silently assumed, so a future multi-
  writer ingestion design knows to revisit it.
- Corporate actions, adjusted price, and the trading calendar remain
  genuinely unimplemented design records - nothing about the revision-
  history change above requires redesigning them; a
  `get_adjusted_bars_as_of` built later reads the same `market_bars`
  revision history this ADR now implements, it just also joins
  `corporate_actions`.
