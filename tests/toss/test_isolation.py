"""Statically proves `app.research` has no import edge to `app.toss`
(or `app.data`/`app.brokers`), per instruction 10 for this phase and
ADR 0001/0006/0007.
"""

from __future__ import annotations

import ast
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parents[2] / "app" / "research"
FORBIDDEN_IMPORT_PREFIXES = ("app.toss", "app.data", "app.brokers")


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_research_package_never_imports_toss_data_or_brokers() -> None:
    offending: list[str] = []
    for path in RESEARCH_DIR.rglob("*.py"):
        for module in _imported_modules(path):
            if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                offending.append(f"{path}: imports {module}")

    assert offending == []
