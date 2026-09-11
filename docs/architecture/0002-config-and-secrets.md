# ADR 0002: Configuration and secret handling

## Status
Accepted (Phase 00)

## Context
The platform needs Toss API credentials and, eventually, a database
URL. These must never be committed to git, and behavior needs to
differ between local development, automated tests, and (eventually)
production.

## Decision
- `app.core.config.Settings` (a `pydantic-settings` `BaseSettings`
  subclass) is the single source of truth for configuration. All
  fields have safe defaults or are `None` - nothing required is
  hardcoded.
- Secrets (`toss_api_key`, `toss_api_secret`) are typed as
  `pydantic.SecretStr`, so they never appear in `repr()`/logs by
  accident; callers must explicitly call `.get_secret_value()`.
- `APP_ENV` (`dev` | `test` | `prod`, `app.core.config.Environment`)
  selects the running environment. Settings are loaded from a local
  `.env` file (via `pydantic-settings`' built-in support), which is
  gitignored. `.env.example` is committed as the template and must
  never contain a real credential.
- Test isolation: `tests/conftest.py` has an autouse fixture that
  forces `APP_ENV=test` and clears the `get_settings()` cache before
  and after every test, so the suite can never accidentally read a
  developer's real `.env`. Tests that need specific values construct
  `Settings(_env_file=None, **overrides)` directly, or set environment
  variables via `monkeypatch`.
- `get_settings()` is a process-wide cached singleton
  (`functools.lru_cache`) so the rest of the app calls one function
  instead of threading a `Settings` object through every constructor.

## Consequences
- Onboarding a new environment is "copy `.env.example` to `.env`, fill
  in values" - no code changes needed.
- Because no adapter code exists yet, no field name for the Toss API
  request/response payloads is assumed anywhere in `Settings` - only
  the base URL and credentials, which are operational config, not
  response schema.
- If production configuration needs secrets manager integration later
  (AWS Secrets Manager, Vault, ...), that becomes a new `Settings`
  source loaded before the `.env` file, without changing the public
  `get_settings()` API.
