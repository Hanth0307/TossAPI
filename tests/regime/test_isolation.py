"""Statically proves the Phase 05 `app.regime` module boundary: no
import edge to `app.toss`, `app.research`, `app.ingest`, `app.brokers`,
`app.risk`, or `app.execution`, and `classifier.py` (pure logic) has
no database import - only `provider.py` touches `app.db`.
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


def test_app_regime_has_no_import_edge_to_forbidden_packages() -> None:
    forbidden = (
        "app.toss", "app.research", "app.ingest", "app.brokers", "app.risk", "app.execution",
    )
    offending = []
    for path in (REPO_ROOT / "app" / "regime").rglob("*.py"):
        for module in _imported_modules(path):
            if module.startswith(forbidden):
                offending.append(f"{path}: imports {module}")
    assert offending == []


def test_app_regime_classifier_has_no_database_import() -> None:
    """`classifier.py` may import row/type dataclasses from
    `app.db.repositories.*` (no SQL of its own results from that) -
    what it must never import is anything that can issue a query:
    `app.db.engine`/`app.db.upsert` or `sqlalchemy` itself. Only
    `provider.py` does that - see `app/regime/__init__.py`.
    """
    path = REPO_ROOT / "app" / "regime" / "classifier.py"
    offending = []
    for module in _imported_modules(path):
        is_query_capable = module.startswith("app.db.engine") or module.startswith("app.db.upsert")
        is_sqlalchemy_import = module == "sqlalchemy" or module.startswith("sqlalchemy.")
        if is_query_capable or is_sqlalchemy_import:
            offending.append(module)
    assert offending == []
