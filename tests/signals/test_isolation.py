"""Statically proves the Phase 05 `app.signals` module boundary: no
import edge to `app.toss`, `app.research`, `app.ingest`, `app.brokers`,
`app.risk`, or `app.execution` - **no order is generated anywhere in
this package**, which the `app.brokers`/`app.execution` check exists
to prove structurally, not just by convention.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_app_signals_has_no_import_edge_to_forbidden_packages() -> None:
    forbidden = (
        "app.toss", "app.research", "app.ingest", "app.brokers", "app.risk", "app.execution",
    )
    offending = []
    for path in (REPO_ROOT / "app" / "signals").rglob("*.py"):
        for module in _imported_modules(path):
            if module.startswith(forbidden):
                offending.append(f"{path}: imports {module}")
    assert offending == []


def test_app_signals_schema_has_no_database_import() -> None:
    path = REPO_ROOT / "app" / "signals" / "schema.py"
    offending = []
    for module in _imported_modules(path):
        is_query_capable = module.startswith("app.db.engine") or module.startswith("app.db.upsert")
        is_sqlalchemy_import = module == "sqlalchemy" or module.startswith("sqlalchemy.")
        if is_query_capable or is_sqlalchemy_import:
            offending.append(module)
    assert offending == []
