"""Scanner pipeline (Phase 04): Market -> Universe Filter -> Event
Scanner -> Strategy Scanner -> Candidate.

Depends on `app.core` and `app.db` only - `app.scanners` has no
import edge to `app.toss`, `app.research`, `app.ingest`, `app.brokers`,
`app.risk`, or `app.execution`. It reads exclusively through
`app.db.repositories` (populated by `app.ingest` from `app.toss`,
Phase 03) - it never calls an external API itself, so every scanner
run is exactly as point-in-time-safe as the repositories it reads
through: every fetch is `as_of`-gated, and a correction ingested after
a scan can never change what that scan already returned (ADR 0008/
0009). See docs/architecture/0010-scanner-pipeline.md.

Only `app.scanners.pipeline` and `app.scanners.persistence` touch
`app.db` - `universe.py`, `events.py`, `strategy_rules.py`, and
`candidate.py` are pure logic over already-fetched data, so every
filter/event/condition is testable with a fixed fixture and no
database at all (see `tests/scanners/`).

**A `Candidate` is a research artifact, never an order.** Nothing in
this package places, suggests, or triggers a trade - `app.brokers`/
`app.execution` remain interface-only (Phase 00) regardless of what a
Candidate's `qualified` flag says.

**No sentiment/quality score is invented.** News/disclosure "events"
here are existence/count-based only (`NewsOccurrenceEventScanner`,
`DisclosureOccurrenceEventScanner`) - there is no AI/sentiment model
in this codebase yet, and none is fabricated here to stand in for one.

**Strategy conditions are not parsed from `StrategySpec` prose.**
`app.research.models.StrategySpec.entry_rules`/`exit_rules` (Phase 01)
are free-text research documentation, not executable logic (ADR 0006).
`app.scanners.strategy_rules.StrategyRuleSet` is a separate, structured,
human-authored companion referencing the same `(strategy_id, version)`
for traceability - turning prose into a machine-checkable condition is
a deliberate authoring step, never an automatic inference this package
performs.
"""
