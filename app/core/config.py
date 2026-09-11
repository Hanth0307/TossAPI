"""Application settings, loaded from environment variables / `.env`.

Environment separation: the `APP_ENV` variable (dev | test | prod)
selects the environment. Real secrets live only in a local, gitignored
`.env` file (see `.env.example` for the template) - nothing here
hardcodes a credential.

Tests must never depend on a developer's real `.env`: `tests/conftest.py`
forces `APP_ENV=test` and clears the settings cache before each test,
and Settings can always be instantiated directly with `_env_file=None`
plus explicit keyword overrides to bypass file loading entirely.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Environment = Environment.DEV
    log_level: str = "INFO"
    log_format: str = "console"

    database_url: str | None = None

    # Base URL and field names are intentionally left unset - do not
    # assume a value here. Verify against the official Toss API docs
    # / real responses before any adapter depends on them.
    toss_api_base_url: str | None = None
    toss_api_key: SecretStr | None = None
    toss_api_secret: SecretStr | None = None

    http_timeout_seconds: float = 10.0
    http_max_retries: int = 3

    # Hard safety default. Must stay True until a reviewed live-broker
    # adapter exists; Phase 00 ships no order-placing code at all.
    paper_trading_only: bool = True


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings singleton.

    Call `get_settings.cache_clear()` (done automatically by the
    `tests/conftest.py` fixture) if settings need to be reloaded, e.g.
    after changing environment variables at runtime.
    """
    return Settings()
