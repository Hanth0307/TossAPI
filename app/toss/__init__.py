"""Toss Open API integration - Market Data Gateway and Portfolio Read Gateway.

Depends on `app.core` and `app.adapters` only - `app.toss` has no
import edge to `app.research`, `app.strategies`, `app.risk`, or
`app.execution` (see docs/architecture/0007-toss-api-integration.md
and docs/architecture/0001-module-boundaries.md).

**Read-only, Phase 02.** Nothing in this package can place, modify,
or cancel an order: `TossRestClient` exposes only `get()` (no
`post`/`put`/`delete`), and construction fails immediately unless
`Settings.toss_read_only_mode` is `True` (the code-level feature flag
required for this phase - see `app.toss.factory`). The official
POST /api/v1/orders (and modify/cancel) endpoints exist per the docs
but are deliberately not implemented anywhere in this codebase.

Every endpoint this package calls is confirmed against the official
Toss Open API docs (base URL, auth flow, endpoint paths). Response
*field-level* schemas are only asserted where an official example was
available (current price, orderbook, trades, candles) - see
`app/toss/dto.py` and ADR 0007 for exactly which endpoints fall back
to an opaque, raw-preserving `UnparsedRecord` pending confirmed
field names. The OAuth token response is a special case of this: its
fields were never shown either, so parsing it is isolated behind a
swappable, explicitly-provisional boundary - see
`app/toss/token_parser.py`.

No WebSocket client exists here. The official docs confirm Toss
offers one but no protocol detail (URL, auth, message envelope,
heartbeat, reconnect policy) has been verified - see the WebSocket
status block in `app/toss/market_data.py` and ADR 0007.
"""
