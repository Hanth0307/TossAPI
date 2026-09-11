"""Application exception hierarchy.

Every error raised by this codebase should subclass `AppError` so
callers can catch application errors as a group without accidentally
swallowing unrelated bugs (KeyError, TypeError, ...).

Order-related errors live under `OrderError` on purpose and are kept
separate from generic `ExternalAPIError`s: order calls are never
auto-retried (see docs/architecture/0004-external-api-timeout-retry-policy.md),
so an `OrderError` always means "ask a human / risk engine before
trying again", never "safe to retry".
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all application-raised errors."""


class ConfigError(AppError):
    """Invalid or missing configuration/environment settings."""


class ExternalAPIError(AppError):
    """Base class for errors while calling or parsing an external API."""


class ExternalAPITimeoutError(ExternalAPIError):
    """An external API call exceeded its configured timeout."""


class ExternalAPIRetryExhaustedError(ExternalAPIError):
    """All configured retry attempts were exhausted without success."""


class ExternalAPIAuthError(ExternalAPIError):
    """Authentication/authorization failed against an external API."""


class DataValidationError(AppError):
    """Received data did not match the expected shape/contract.

    Raise this instead of guessing at a missing/renamed field - never
    silently substitute an assumed field name.
    """


class OrderError(AppError):
    """Base class for order-related errors.

    Deliberately NOT a subclass of `ExternalAPIError`: order failures
    must never be handled by generic retry logic.
    """


class RiskViolationError(OrderError):
    """An order or action was blocked by a risk-engine rule."""


class BrokerError(OrderError):
    """A broker adapter failed to process a request."""


class BacktestError(AppError):
    """Invalid backtest configuration or a failure during a backtest run."""


class ResearchError(AppError):
    """Base class for Strategy Research Lab (`app.research`) errors."""


class StrategyVersionExistsError(ResearchError):
    """A spec for this (strategy_id, version) already exists in the registry.

    The Strategy Registry is append-only by default so a saved
    research result stays reproducible - pass `overwrite=True` to
    `StrategyRegistry.save()` if replacing it is genuinely intended.
    """


class StrategyNotFoundError(ResearchError):
    """No spec was found for the requested strategy_id/version."""


class TossApiError(ExternalAPIError):
    """Base class for Toss Open API errors that carry an HTTP status.

    Subclasses distinguish the failure modes the official docs call
    out explicitly (see docs/architecture/0007-toss-api-integration.md):
    401 authentication, 403 IP allow-list rejection, 429 per-group
    rate limiting, and 5xx server-side failures. None of these are
    ever treated as "no data" or silently swallowed into a stale
    result - see `app.toss.error_mapping.raise_for_status`.
    """

    def __init__(
        self, message: str, *, status_code: int | None = None, error_code: str | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class TossAuthenticationError(TossApiError):
    """401 - the access token was missing, invalid, or expired (even after one refresh)."""


class TossIpRestrictedError(TossApiError):
    """403 - the caller's IP is not registered in the Toss Open API allow-list.

    Per the official docs, Open API settings require registering
    caller IPs; an unregistered IP is rejected with 403.
    """


class TossRateLimitError(TossApiError):
    """429 - the per-group TPS limit was exceeded.

    `error_code` is one of the confirmed values (`edge-rate-limit-exceeded`,
    `rate-limit-exceeded`) when the response body could be parsed.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 429,
        error_code: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, error_code=error_code)
        self.retry_after = retry_after


class TossServerError(TossApiError):
    """5xx - a Toss-side failure (confirmed codes include `internal-error`, `maintenance`)."""
