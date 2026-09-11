"""Statically proves no WebSocket client exists yet under app/toss.

Toss's official marketing page confirms a WebSocket offering exists,
but no protocol detail (URL, auth, subscribe protocol, message
envelope, heartbeat, reconnect policy) has been verified - see the
status block in app/toss/market_data.py and ADR 0007. This test is the
structural proof that nothing was implemented against a guessed
protocol.
"""

from __future__ import annotations

import ast
from pathlib import Path

TOSS_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "app" / "toss"


def _all_py_files() -> list[Path]:
    return list(TOSS_PACKAGE_DIR.rglob("*.py"))


def test_no_file_named_for_websocket_functionality() -> None:
    offending = [
        path.name
        for path in _all_py_files()
        if "websocket" in path.name.lower() or "ws_" in path.name.lower()
    ]
    assert offending == []


def test_no_class_defines_websocket_functionality() -> None:
    offending: list[str] = []
    for path in _all_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "websocket" in node.name.lower():
                offending.append(f"{path}:{node.lineno}:{node.name}")

    assert offending == []


def test_no_websocket_url_scheme_appears_anywhere() -> None:
    offending: list[str] = []
    for path in _all_py_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "ws://" in line or "wss://" in line:
                offending.append(f"{path}:{lineno}")

    assert offending == []


def test_market_data_adapter_exposes_no_streaming_or_subscribe_method() -> None:
    from app.toss.market_data import MarketDataAdapter

    public_methods = {name for name in dir(MarketDataAdapter) if not name.startswith("_")}
    forbidden = {"subscribe", "unsubscribe", "connect", "stream", "on_message", "listen"}
    assert public_methods.isdisjoint(forbidden)
