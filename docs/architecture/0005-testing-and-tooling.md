# ADR 0005: Testing, linting, and type-checking setup

## Status
Accepted (Phase 00)

## Context
The project needs a repeatable way to verify correctness (pytest),
catch obvious bugs/style issues early (a linter), and catch type
errors before runtime (a type checker), without adding tooling
overhead disproportionate to a project-skeleton phase.

## Decision
- **pytest** (`[tool.pytest.ini_options]` in `pyproject.toml`,
  `testpaths = ["tests"]`) is the test runner. `pytest-cov` is
  included for coverage reporting (`make test` runs with
  `--cov=app`).
- Test isolation from real secrets/environment is handled by the
  autouse fixture in `tests/conftest.py` (see ADR 0002) rather than by
  a separate `.env.test` file - one less file to keep in sync, and it
  makes the isolation mechanism visible in code instead of config.
- External HTTP calls are tested against `httpx.MockTransport`
  (`tests/adapters/test_http_client.py`) - no real network access is
  needed to run the suite, and none of the adapter tests are flaky
  because of it.
- **ruff** is used for both linting and import sorting (`select = ["E",
  "F", "I", "UP", "B"]` in `pyproject.toml`) - one fast tool instead of
  separate flake8/isort/pyupgrade installs.
- **mypy** is used for static type checking (`[tool.mypy]` in
  `pyproject.toml`). `ignore_missing_imports = true` because
  third-party stubs aren't guaranteed to exist yet for every future
  dependency; this can be tightened per-package as real integrations
  are added.
- A `Makefile` exposes `make install`, `make test`, `make lint`,
  `make typecheck`, and `make check` (all three) as the standard local
  commands - matches what a CI pipeline would run, without committing
  to a specific CI provider yet.

## Consequences
- `pip install -e ".[dev]"` plus `make check` is the full verification
  loop for any contributor or CI system, with no hidden setup steps.
- Because the test suite never touches the network or a real `.env`,
  it is deterministic and safe to run in any environment, including
  CI runners with no outbound access.
- No CI workflow file (e.g. GitHub Actions) is added in Phase 00 to
  avoid speculating about the eventual CI provider/secrets setup; the
  `Makefile` targets are written so wiring one up later is a small,
  mechanical step.
