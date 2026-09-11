# ADR 0003: Structured logging and exception hierarchy

## Status
Accepted (Phase 00)

## Context
A quant/trading system needs log lines that are greppable/aggregable
(symbol, order id, reason codes as structured fields, not just free
text) and an exception hierarchy that lets calling code distinguish
"safe to retry", "external API problem", and "order-related - do not
auto-retry" at a glance.

## Decision
**Logging** (`app.core.logging`):
- Standard library `logging`, not a third-party structured-logging
  package - Phase 00's needs (one JSON formatter, one console
  formatter) don't justify the extra dependency.
- `JsonFormatter` renders each record as one JSON line: timestamp
  (UTC, ISO-8601), level, logger name, message, and any fields passed
  via `extra={"extra_fields": {...}}`.
- `configure_logging(level, fmt)` replaces the root logger's handlers
  so it is safe to call more than once (e.g. once in app startup,
  once again in a test that wants a specific level).
- `LOG_FORMAT=json` for production/aggregated logs, `console` (plain
  text) for local development - controlled by `Settings.log_format`.

**Exceptions** (`app.core.exceptions`):
- Single root: `AppError(Exception)`. All application-raised errors
  subclass it, so application code can do
  `except AppError: ...` to mean "an error I anticipated", separate
  from unexpected bugs.
- `ExternalAPIError` and its subclasses (`ExternalAPITimeoutError`,
  `ExternalAPIRetryExhaustedError`, `ExternalAPIAuthError`) represent
  transport-level failures talking to an external API. These are safe
  to catch generically and are what `app.adapters.http_client` raises.
- `OrderError` (and its subclasses `RiskViolationError`,
  `BrokerError`) is **not** a subclass of `ExternalAPIError`, on
  purpose. Order-related failures must never be handled by the same
  generic "log and retry" code path as a read-only API call - see ADR
  0004. `tests/core/test_exceptions.py` asserts this relationship so
  the separation cannot silently regress.
- `DataValidationError` is raised when a response doesn't match the
  shape a caller expected, instead of the caller guessing a field name
  (see the project-level rule against inventing API fields).

## Consequences
- Any code that wraps a broad `try/except AppError` will never
  accidentally swallow an `OrderError` as if it were a retryable
  transport error.
- Adding a new error type is a one-line addition to
  `app/core/exceptions.py`, with the review question "does this belong
  under `ExternalAPIError` or `OrderError`?" made explicit by the
  module's docstring.
