from __future__ import annotations

import pytest

from app.core.config import Environment, Settings, get_settings


def test_settings_default_env_file_only(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    # The autouse fixture forces APP_ENV=test for the whole suite;
    # unset it here to check the true default value.
    monkeypatch.delenv("APP_ENV", raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_env == Environment.DEV
    assert settings.paper_trading_only is True
    assert settings.toss_api_key is None


def test_settings_reads_app_env_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    settings = Settings(_env_file=None)
    assert settings.app_env == Environment.TEST


def test_settings_secret_not_exposed_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOSS_API_KEY", "super-secret-value")
    settings = Settings(_env_file=None)
    assert "super-secret-value" not in repr(settings)
    assert settings.toss_api_key is not None
    assert settings.toss_api_key.get_secret_value() == "super-secret-value"


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
