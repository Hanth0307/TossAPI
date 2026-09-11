# ADR 0004: External API timeout/retry policy, and why orders are different

## Status
Accepted (Phase 00)

## Context
Every external integration (Toss API, DART, news providers, and
eventually a live broker) needs a timeout and a retry policy. A single
global "retry N times on failure" policy is unsafe for order-mutating
calls: if a `place_order` request times out after the broker actually
received and processed it, blindly retrying submits a second, real
order. Read-only calls (quotes, balances, news) have no such risk.

## Decision
`app.adapters.http_client` defines:
- `RetryPolicy` - a frozen dataclass: `timeout_seconds`, `max_retries`,
  `backoff_base_seconds`, `backoff_multiplier`, `retry_status_codes`.
- `DEFAULT_RETRY_POLICY` - `max_retries=3`, exponential backoff, retries
  on timeouts and on `{408, 429, 500, 502, 503, 504}`. Intended for
  read-only / idempotent calls.
- `NO_RETRY_POLICY` - `max_retries=0`. **Required** for any
  order-mutating call (place/cancel/modify order). A failure raises
  immediately instead of retrying automatically.
- `BaseApiClient.request(method, path, **kwargs)` applies whichever
  policy it was constructed with, and raises
  `ExternalAPITimeoutError` / `ExternalAPIRetryExhaustedError` /
  `ExternalAPIError` (see ADR 0003) rather than returning a failed
  response silently past the retry budget.

This is a transport-level control only. It is not sufficient by
itself: any future broker adapter (`app.brokers`) must also pass a
`client_order_id` on `OrderRequest` so that if a human or the
execution engine does decide to resubmit after a confirmed failure,
the broker can de-duplicate. `app.execution.ExecutionEngine`'s
docstring records this expectation for the implementation that will
eventually fulfill it.

## Consequences
- Every adapter built on `BaseApiClient` gets consistent timeout/retry
  behavior for free, and cannot use retries on an order call without
  explicitly passing `NO_RETRY_POLICY` - the safe default
  (`DEFAULT_RETRY_POLICY`) is the *wrong* choice for orders, so the
  code review question is simply "is this call order-mutating? then
  it must say `NO_RETRY_POLICY` explicitly."
- `tests/adapters/test_http_client.py` verifies both policies'
  behavior against a mocked transport (`httpx.MockTransport`), so this
  guarantee is regression-tested without any real network call.
- No live order-placing code exists yet (forbidden in Phase 00); this
  ADR exists so that when it is built, the timeout/retry decision is
  already made and tested.
