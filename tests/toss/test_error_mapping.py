from __future__ import annotations

import httpx
import pytest

from app.core.exceptions import TossApiError
from app.toss.error_mapping import extract_error_code, extract_retry_after_seconds, raise_for_status


def test_extract_error_code_handles_top_level_code() -> None:
    response = httpx.Response(429, json={"code": "rate-limit-exceeded"})
    assert extract_error_code(response) == "rate-limit-exceeded"


def test_extract_error_code_handles_string_error_field() -> None:
    response = httpx.Response(500, json={"error": "internal-error"})
    assert extract_error_code(response) == "internal-error"


def test_extract_error_code_handles_nested_error_code() -> None:
    response = httpx.Response(500, json={"error": {"code": "maintenance"}})
    assert extract_error_code(response) == "maintenance"


def test_extract_error_code_returns_none_for_non_json_body() -> None:
    response = httpx.Response(500, content=b"not json")
    assert extract_error_code(response) is None


def test_extract_error_code_returns_none_for_non_dict_json() -> None:
    response = httpx.Response(500, json=["unexpected", "list"])
    assert extract_error_code(response) is None


def test_extract_retry_after_seconds_parses_numeric_header() -> None:
    response = httpx.Response(429, headers={"Retry-After": "5"})
    assert extract_retry_after_seconds(response) == 5.0


def test_extract_retry_after_seconds_returns_none_when_absent() -> None:
    response = httpx.Response(429)
    assert extract_retry_after_seconds(response) is None


def test_extract_retry_after_seconds_returns_none_for_non_numeric_header() -> None:
    response = httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
    assert extract_retry_after_seconds(response) is None


def test_raise_for_status_is_a_noop_for_2xx() -> None:
    raise_for_status(httpx.Response(200), context="test")  # must not raise


def test_raise_for_status_raises_generic_error_for_unexpected_status() -> None:
    with pytest.raises(TossApiError) as excinfo:
        raise_for_status(httpx.Response(418, json={}), context="GET /api/v1/prices")
    assert excinfo.value.status_code == 418
