# ADR 0009: Corporate actions, adjusted price, and full bi-temporal history (future extension)

## Status
Accepted (Phase 03) - **design record only, nothing in this ADR is
implemented yet.** It exists so Phase 03's schema does not have to be
redesigned when this work happens; it commits to nothing beyond that.

## Context
Two known gaps in the Phase 03 Data Platform (ADR 0008), both
explicitly out of scope for this phase but easy to paint into a
corner on if left undocumented:

1. **Corporate actions / adjusted price.** `market_bars` stores raw
   OHLCV as reported. A stock split, dividend, or other corporate
   action changes what a historical price *means* relative to the
   current share count/price basis - a backtest or model spanning such
   an event needs an adjusted series, but adjustment is a derived
   view, not a fact about what actually printed. Storing only an
   adjusted price (or only a raw price) loses information either way.
2. **Full bi-temporal history.** ADR 0008 documents that a correction
   to an already-ingested row updates it in place, preserving the
   *original* `available_at` but not what the *value* was at every
   point in between. A query "as of T" after a correction sees the
   corrected value even if T predates the correction - acceptable for
   Phase 03's scope (there are no real corrections happening yet -
   this codebase does not even ingest from a live feed continuously),
   but a real gap for a system that needs to reconstruct exactly what
   was knowable at each historical instant, not just whether it was
   knowable at all.
3. **No trading calendar.** `app.db.quality.compute_market_data_quality`
   estimates missing bars from a fixed interval, which over-counts
   "missing" for calendar-gapped timeframes (daily bars skip weekends/
   holidays). A real trading calendar would fix this.

## Decision (for a future phase to implement, not now)

### Corporate actions
Add a `corporate_actions` table (not created by this ADR):
`instrument_id`, `action_type` (split, dividend, ...), `event_time`
(ex-date), `available_at`/`ingested_at` (same convention as every
other observed-event table), and action-specific factors (e.g. a
split ratio) in a `details` `JSONB` column until a real source's exact
field names are confirmed - following the same "raw JSONB until
confirmed" discipline as `account_snapshots` (ADR 0007).

Adjustment stays a **read-time computation**, never a mutation of
`market_bars`: a future `AdjustedPriceView` (or a repository method
`get_adjusted_bars_as_of(...)`) would fold `corporate_actions` rows
between a bar's `event_time` and the query's `as_of` into an
adjustment factor applied on the way out. This keeps `market_bars` an
immutable record of what was actually reported - the same principle
that keeps raw and normalized data separate throughout ADR 0008 - and
means an adjustment methodology can change (or be wrong and get fixed)
without rewriting historical rows.

### Full bi-temporal versioning
Where reconstructing the *exact* historical answer at every `as_of`
matters (not just "was it available yet"), the fix is to stop
updating observed-event rows in place on conflict and instead insert
a new row per correction, keyed additionally on `available_at` (making
it part of the natural key rather than excluded from every `UPDATE`).
A point-in-time read then becomes "the row with the greatest
`available_at <= as_of`, per `event_time`" (a `DISTINCT ON` query, the
same shape `PositionRepository.get_current_positions_as_of` already
uses in Phase 03) rather than "the one current row". This is a
mechanical, additive change to `app.db.upsert`/`app.db.repositories` -
it does not require a schema rewrite, only relaxing "one row per
natural key" to "one row per (natural key, available_at)" for the
tables where it turns out to matter.

### Trading calendar
A `trading_calendar` reference table (`exchange`, `date`,
`is_trading_day`) - populated from a real exchange calendar source
once one is integrated - would let `compute_market_data_quality`
compute `expected_bar_count` from actual trading days instead of a
fixed interval, removing the documented weekend/holiday over-count.

## Consequences
- Phase 03 ships none of this - `market_bars` has no adjustment
  column, no `corporate_actions` table exists, upserts still update in
  place, and quality metrics still use a fixed-interval estimate. Every
  one of those is called out as a known, documented limitation in ADR
  0008 rather than silently assumed away.
- None of the three extensions above require touching `app.toss`,
  `app.research`, or any table's natural key columns that already
  exist - they are additive (new table, new read-time computation,
  relaxed uniqueness) precisely so this phase's schema does not need
  to be redesigned to accommodate them later.
