from __future__ import annotations

from app.core.exceptions import (
    AppError,
    BacktestError,
    BrokerError,
    ConfigError,
    DataValidationError,
    ExternalAPIAuthError,
    ExternalAPIError,
    ExternalAPIRetryExhaustedError,
    ExternalAPITimeoutError,
    OrderError,
    RiskViolationError,
)


def test_all_exceptions_derive_from_app_error() -> None:
    for exc_type in (
        ConfigError,
        ExternalAPIError,
        ExternalAPITimeoutError,
        ExternalAPIRetryExhaustedError,
        ExternalAPIAuthError,
        DataValidationError,
        OrderError,
        RiskViolationError,
        BrokerError,
        BacktestError,
    ):
        assert issubclass(exc_type, AppError)


def test_order_errors_are_not_external_api_errors() -> None:
    # Order failures must never be caught by generic external-API retry
    # handling - they need explicit, non-automatic handling.
    assert not issubclass(OrderError, ExternalAPIError)
    assert not issubclass(RiskViolationError, ExternalAPIError)
    assert not issubclass(BrokerError, ExternalAPIError)


def test_risk_and_broker_errors_are_order_errors() -> None:
    assert issubclass(RiskViolationError, OrderError)
    assert issubclass(BrokerError, OrderError)
