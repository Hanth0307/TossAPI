# ADR 0007: Toss Open API integration (Phase 02, read-only)

## Status
Accepted (Phase 02)

## Context
Phase 02 connects the platform to the real Toss Investment Open API
as a **Market Data Gateway** and a **Portfolio Read Gateway** - read
only, no order placement. This session's network egress policy blocks
`*.tossinvest.com` entirely (confirmed via direct `curl` to
`developers.tossinvest.com`, `corp.tossinvest.com`, and
`openapi.tossinvest.com`, each rejected with `403 CONNECT tunnel
failed` - an organization policy denial, not a transient failure).
Third-party sources (an unofficial community SDK, blog posts) could
not be treated as ground truth per the project rule against inventing
unconfirmed response fields.

The user therefore verified the official docs out-of-band and
provided the confirmed spec directly in-conversation: base URL, the
OAuth2 flow, the 13 in-scope endpoint paths, and JSON examples for
four of them (current price, orderbook, recent trades, candles).
Everything implemented below is scoped to exactly that confirmed
information - nothing beyond it was guessed.

## Decision

### Auth: OAuth 2.0 Client Credentials Grant
`app.toss.auth.TossOAuthClient` implements `POST /oauth2/token`
(`grant_type=client_credentials`, form-encoded `client_id`/
`client_secret`), caches the token in memory, and refetches when
within `expiry_leeway_seconds` (default 30s) of expiry or when
`invalidate()` is called (used after a 401).

**The token *response* JSON schema itself was never confirmed** - the
provided spec confirmed the grant type and the request shape, not a
response example. Using OAuth 2.0 Client Credentials and returning
`{"access_token": ..., "expires_in": ...}` are two different claims;
only the first is confirmed. `app/toss/token_parser.py` makes this
explicit rather than presenting the second as fact:
- `ProvisionalTokenResponseDto` (`access_token`, `expires_in`) is
  labeled, in its own docstring, a **provisional adapter assumption**
  based on the RFC 6749 §5.1 standard response for this grant type -
  not a confirmed Toss schema.
- `TOKEN_RESPONSE_SCHEMA_VERIFIED = False` records that state
  explicitly; it is only ever flipped to `True` alongside real
  evidence (an observed response body), in the same change that
  updates this ADR.
- Parsing is fail-closed: a response that doesn't match raises
  `DataValidationError` immediately - `TossOAuthClient` never falls
  back to a default or returns a partially-built token
  (`tests/toss/test_token_parser.py::test_unexpected_token_response_shape_fails_closed`).
  The raised message never includes the raw response body or any
  parsed field value, so a token/secret-looking value in an
  unexpected field of a malformed response cannot leak through it
  (`test_token_parsing_failure_never_leaks_response_body_or_secrets`).
- The parser is isolated behind the `TokenResponseParser` protocol and
  injected into `TossOAuthClient` (`token_parser=`) rather than
  hardcoded - `TossOAuthClient` never sees a JSON field name. Once a
  real response is observed, only `app/toss/token_parser.py` needs to
  change (correct the DTO, flip the verified flag); `TossOAuthClient`
  and every caller are untouched.

### Raw DTO vs. normalized domain model split
`app/toss/dto.py` holds one pydantic model per endpoint whose JSON was
shown verbatim (`PriceDto`, `OrderbookDto`, `TradeDto`, `CandleDto`,
plus their list/`result`-envelope wrappers), each with `extra="ignore"`
so an undocumented field Toss adds later cannot break parsing of known
fields. `app/toss/models.py` holds the normalized domain types
(`Quote`, `OrderBookSnapshot`, `TradeTick`, `Candle`/`CandleSeries`)
that `market_data.py` builds from those DTOs - `Decimal` for every
price/quantity (never `float`), timezone-aware `datetime` for every
timestamp (`app/toss/conversions.py` rejects naive datetimes and
unparseable strings outright, raising `DataValidationError`). If Toss
ever renames a DTO field, only `market_data.py`/`portfolio.py` change;
nothing downstream does.

**The other 9 endpoints** (`price-limits`, `stocks`, `accounts`,
`holdings`, `orders`, `orders/{orderId}`, `buying-power`,
`sellable-quantity`, `commissions`) came with a confirmed path but no
JSON example. Inventing field names for them would violate the "never
guess an unconfirmed response field" rule, so they return
`UnparsedRecord` (`app/toss/models.py`): the confirmed `{"result":
...}` envelope is unwrapped and validated, but `result` itself is
preserved as opaque `Any`, unmodified. This still satisfies "Account
responses go through a normalized model" in the structural sense
required by this phase - every record, confirmed-schema or not, gets
the same `RecordMetadata` envelope (below) - while never asserting a
business field that was never shown. Adding a dedicated DTO/model for
any of these nine is a small, additive change once its schema is
confirmed; nothing about this shape needs to change to do that.

### Provenance metadata on every record
Every returned record carries `RecordMetadata`: `source` (constant
`"toss_openapi"`), `event_time` (the response's own timestamp field,
parsed to a timezone-aware `datetime` - `None` where no confirmed
timestamp field exists, e.g. account/holdings/orders and the
per-series metadata on `CandleSeries`, whose individual `Candle`s each
carry their own `timestamp`), and `available_at`/`ingested_at` (both
set to the moment `TossRestClient` received the HTTP response - equal
to each other in this phase because there is no separate ingestion
pipeline yet; a future caching/queue layer would be where they
diverge). `raw_payload` is attached only when the caller opts in via
`capture_raw_payload=True` on `MarketDataAdapter`/`PortfolioReadAdapter`
(default `False`), for debug/audit use without retaining it by
default.

### Errors: precise, never silently stale
`app.toss.error_mapping.raise_for_status` dispatches primarily on HTTP
status - the one thing the docs confirm unambiguously: 401 ->
`TossAuthenticationError`, 403 -> `TossIpRestrictedError` (the docs
tie 403 specifically to an unregistered caller IP in the Open API
allow-list), 429 -> `TossRateLimitError` (carrying `retry_after` from
the standard `Retry-After` header when present, and `error_code` when
the body parses to one of the confirmed strings
`edge-rate-limit-exceeded`/`rate-limit-exceeded`), 5xx ->
`TossServerError` (`error_code` `internal-error`/`maintenance` when
present). All four subclass `ExternalAPIError` (ADR 0003), not
`OrderError` - these are read failures, not order failures. A 401 on
any `TossRestClient.get()` call triggers exactly one token
invalidate-and-retry (ordinary expiry); anything past that raises.
Nothing in `app.toss` ever returns a cached/default value in place of
a failed call - a timeout still raises `ExternalAPITimeoutError`
(ADR 0004's existing exception, unchanged), and a 429/5xx still raises
after retries are exhausted (`app/toss/_retry.py`).

### Rate limiting: confirmed TPS, inferred grouping
The docs confirm four groups and TPS caps (AUTH 5, ACCOUNT 1, ASSET 5,
STOCK 5) but not which of the 13 endpoints belongs to which group
beyond what their own category labels imply.
`app/toss/client.py::DEFAULT_ENDPOINT_GROUPS` maps endpoints whose
category name literally matches a group name (`/api/v1/accounts` ->
ACCOUNT, `/api/v1/holdings` -> ASSET, all Market Data/Stock Info
endpoints -> STOCK) directly; the Order Read-Only and Order Info
Read-Only endpoints (`orders`, `orders/{id}`, `buying-power`,
`sellable-quantity`, `commissions`) have no literal match, so they
default to the most conservative group (ACCOUNT, 1 TPS) until
confirmed - a safety-first inference, not an assertion of fact, and
trivially overridable per-call via `group=`.
`app/toss/rate_limit.GroupThrottle` paces calls client-side to this
TPS but is pure courtesy - a 429 is still handled precisely regardless
of whether the throttle fired first, since the docs note limits can
change.

### Read-only enforcement (code-level, not just a convention)
Two independent, structural guarantees, not just a documented
intention:
1. `TossRestClient` exposes exactly one HTTP verb, `get()` - no
   `post`/`put`/`delete`/generic `request()`. An order-mutating call
   is not "unimplemented", it is inexpressible through this client.
   `tests/toss/test_client.py::test_client_has_no_write_capable_http_verb`
   and `tests/toss/test_feature_flag.py` statically assert this (via
   `ast` parsing of every file under `app/toss/`) and confirm the only
   `"POST"` reference anywhere in the package is the OAuth token fetch.
2. `Settings.toss_read_only_mode` (default `True`) is checked in
   `TossRestClient.__init__` and `app.toss.factory.build_toss_gateways`
   - either refuses to construct with a `ConfigError` if it is `False`.
   There is no order-placing code anywhere in this codebase regardless;
   this flag exists so adding one later requires one deliberate,
   reviewable change to a `False` default, not a silent capability
   already sitting dormant.

The official `POST /api/v1/orders` (and modify/cancel) endpoints exist
per the docs but are out of scope for this phase and are not called
anywhere in this codebase.

### Isolation from `app.research`
`app.toss` depends on `app.core`/`app.adapters` only (ADR 0001).
`app.research` (`StrategySpec`, the Strategy Registry, the TradingView
MCP health check) has no import edge to `app.toss` -
`tests/toss/test_isolation.py` statically confirms this via `ast`
import parsing, mirroring `tests/research/test_isolation.py`'s
TradingView-outage isolation proof from Phase 01. A Toss API outage
therefore cannot affect strategy research, and a TradingView MCP
outage cannot affect this gateway.

### WebSocket: marketing-confirmed, protocol unverified, deferred
An earlier draft of this ADR stated the official docs read "REST
API만 제공합니다" (REST-only) based on the spec available at the time.
That was corrected: the official Toss Securities Open API introduction
page does state both REST and WebSocket are offered. What remains
unconfirmed is everything needed to actually implement a client
against it - no WebSocket URL, authentication method, subscribe/
unsubscribe protocol, message envelope, heartbeat mechanism, reconnect
policy, or rate/subscription limit has been shown. Status, recorded
explicitly rather than left ambiguous:

```
Capability:     OFFICIAL_MARKETING_CONFIRMED
Protocol:       NOT_VERIFIED
Implementation: DEFERRED
```

No WebSocket client, URL, or message schema is defined anywhere in
this codebase - inventing one from the protocol details alone would be
exactly the kind of unconfirmed-contract guess this phase forbids.
`tests/toss/test_no_websocket_implementation.py` statically confirms
no such class/URL exists yet (`ast`-based, mirroring the other
structural proofs in this package). `MarketDataAdapter` is
REST-polling only for Phase 02. A future `StreamingMarketDataProvider`
-shaped interface can be added once a real protocol document is
available to verify URL/auth/message-format/heartbeat/reconnect
behavior against - not before.

## Consequences
- Every Phase 02 test runs against `httpx.MockTransport` fixtures -
  the 4 confirmed-schema endpoints use the exact official JSON
  examples verbatim (`tests/toss/test_market_data.py`); no test
  depends on network access or real credentials.
  `tests/toss/test_integration_live.py` is the sole opt-in exception
  (`TOSS_INTEGRATION_TEST=1` plus real credentials), always skipped in
  this environment for the reasons above.
- The 9 unconfirmed-schema endpoints are fully callable (correct path,
  auth, headers, rate-limit group, error mapping) but return opaque
  `UnparsedRecord.result` until their schemas are confirmed - see the
  Phase 03 handoff notes in the Phase 02 completion report for exactly
  which fields remain unverified.
- If a future session gets real network access to `*.tossinvest.com`,
  the natural next step is running `test_integration_live.py` for real
  and using its (real) responses to add DTOs for the 9 remaining
  endpoints - no restructuring needed, just additive DTOs/models
  following the same raw-vs-normalized split.
- The same applies to the OAuth token response: a real observed body
  either confirms `ProvisionalTokenResponseDto` as-is (flip
  `TOKEN_RESPONSE_SCHEMA_VERIFIED` to `True`) or shows it needs
  correcting - either way, only `app/toss/token_parser.py` changes.
- WebSocket implementation is fully deferred pending an actual
  protocol document (URL/auth/message format/heartbeat/reconnect) -
  see the status block above. This is not scheduled by this ADR; it
  starts only once that document exists to verify against.
