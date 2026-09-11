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
