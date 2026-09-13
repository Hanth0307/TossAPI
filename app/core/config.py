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

    # Confirmed against the official Toss Open API docs (Phase 02):
    # OAuth 2.0 Client Credentials Grant, POST /oauth2/token, base URL
    # https://openapi.tossinvest.com. Credentials themselves are never
    # defaulted - only the base URL, which is public information.
    toss_api_base_url: str = "https://openapi.tossinvest.com"
    toss_client_id: SecretStr | None = None
    toss_client_secret: SecretStr | None = None
    # X-Tossinvest-Account header value for account/asset/order-read
    # calls. Treated as a secret (never logged) even though it is an
    # identifier rather than a credential - see ADR 0007.
    toss_account_seq: SecretStr | None = None

    http_timeout_seconds: float = 10.0
    http_max_retries: int = 3

    # AI Context extraction (Phase 05, see ADR 0011). Never defaulted -
    # `app.ai_context.claude_extractor.ClaudeContextExtractor` requires
    # an explicit key; its absence is a configuration fact, not a
    # reason to guess or fall back to a hardcoded one.
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5"

    # Hard safety default. Must stay True until a reviewed live-broker
    # adapter exists; Phase 00 ships no order-placing code at all.
    paper_trading_only: bool = True

    # Code-level gate for Phase 02: the Toss adapters refuse to
    # construct at all unless this is True. There is no order-placing
    # code anywhere in app.toss regardless - this flag exists so a
    # future phase must make one deliberate, reviewable change to even
    # begin adding one. See ADR 0007.
    toss_read_only_mode: bool = True


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings singleton.

    Call `get_settings.cache_clear()` (done automatically by the
    `tests/conftest.py` fixture) if settings need to be reloaded, e.g.
    after changing environment variables at runtime.
    """
    return Settings()
