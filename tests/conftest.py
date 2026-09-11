"""Shared pytest fixtures.

Forces APP_ENV=test and clears the cached Settings singleton before
and after every test, so the test suite never reads a developer's
real `.env` file / real secrets.
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _isolated_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
