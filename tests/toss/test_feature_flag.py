"""Verifies the code-level read-only gate required for Phase 02."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.exceptions import ConfigError
from app.toss.auth import TossOAuthClient
from app.toss.client import TossRestClient
from app.toss.factory import build_toss_gateways

TOSS_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "app" / "toss"

FORBIDDEN_METHOD_NAME_SUBSTRINGS = (
    "place_order",
    "create_order",
    "cancel_order",
    "modify_order",
    "amend_order",
)
FORBIDDEN_HTTP_VERBS = {"post", "put", "delete", "patch"}


def test_toss_rest_client_refuses_to_construct_when_read_only_mode_false() -> None:
    oauth = TossOAuthClient(
        base_url="https://openapi.tossinvest.com",
        client_id=SecretStr("id"),
        client_secret=SecretStr("secret"),
    )
    with pytest.raises(ConfigError, match="read_only"):
        TossRestClient(
            base_url="https://openapi.tossinvest.com", oauth_client=oauth, read_only_mode=False
        )


def test_factory_refuses_to_build_gateways_when_read_only_mode_false() -> None:
    settings = Settings(
        _env_file=None,
        toss_client_id=SecretStr("id"),
        toss_client_secret=SecretStr("secret"),
        toss_read_only_mode=False,
    )
    with pytest.raises(ConfigError):
        build_toss_gateways(settings)


def test_factory_refuses_to_build_gateways_without_credentials() -> None:
    settings = Settings(_env_file=None, toss_read_only_mode=True)
    with pytest.raises(ConfigError):
        build_toss_gateways(settings)


def test_factory_builds_gateways_when_read_only_and_credentials_present() -> None:
    settings = Settings(
        _env_file=None,
        toss_client_id=SecretStr("id"),
        toss_client_secret=SecretStr("secret"),
        toss_read_only_mode=True,
    )
    gateways = build_toss_gateways(settings)
    assert gateways.market_data is not None
    assert gateways.portfolio is not None


def test_no_source_file_under_app_toss_defines_a_write_http_method() -> None:
    """Static proof there is no `def post/put/delete/patch(...)` anywhere
    in app.toss - an order-mutating call is not just unimplemented, it
    is not expressible.
    """
    offending: list[str] = []
    for path in TOSS_PACKAGE_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.lower() in FORBIDDEN_HTTP_VERBS:
                offending.append(f"{path}:{node.lineno}:{node.name}")

    assert offending == []


def test_no_source_file_under_app_toss_defines_an_order_mutating_method() -> None:
    offending: list[str] = []
    for path in TOSS_PACKAGE_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                name = node.name.lower()
                if any(forbidden in name for forbidden in FORBIDDEN_METHOD_NAME_SUBSTRINGS):
                    offending.append(f"{path}:{node.lineno}:{node.name}")

    assert offending == []


def test_the_only_post_call_anywhere_in_app_toss_is_the_oauth_token_fetch() -> None:
    """`POST /api/v1/orders` (and modify/cancel) exist per the official
    docs but must not be called anywhere in this codebase during
    Phase 02. The OAuth token fetch (`POST /oauth2/token`) is the one
    legitimate POST - confirm it is the *only* one, in `auth.py`, and
    that nothing outside `auth.py` ever sends a POST at all.
    """
    offending: list[str] = []
    for path in TOSS_PACKAGE_DIR.rglob("*.py"):
        if path.name == "auth.py":
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if '"POST"' in line or "'POST'" in line:
                offending.append(f"{path}:{lineno}")

    assert offending == []

    auth_text = (TOSS_PACKAGE_DIR / "auth.py").read_text(encoding="utf-8")
    assert '"POST"' in auth_text
    assert "/oauth2/token" in auth_text
    assert "/api/v1/orders" not in auth_text
