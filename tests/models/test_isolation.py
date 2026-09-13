"""Statically proves the Phase 05 `app.models` module boundary: no
import edge to `app.toss`, `app.research`, `app.ingest`, `app.brokers`,
`app.risk`, or `app.execution`, and only `dataset.py`/`artifact.py`
touch `app.db` - `labels.py`/`features.py`/`model.py`/`training.py`/
`evaluation.py`/`importance.py` are pure logic.
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


def test_app_models_has_no_import_edge_to_forbidden_packages() -> None:
    forbidden = (
        "app.toss", "app.research", "app.ingest", "app.brokers", "app.risk", "app.execution",
    )
    offending = []
    for path in (REPO_ROOT / "app" / "models").rglob("*.py"):
        for module in _imported_modules(path):
            if module.startswith(forbidden):
                offending.append(f"{path}: imports {module}")
    assert offending == []


def test_app_models_pure_logic_modules_have_no_query_capable_import() -> None:
    models_dir = REPO_ROOT / "app" / "models"
    pure_logic_files = [
        models_dir / "labels.py",
        models_dir / "features.py",
        models_dir / "model.py",
        models_dir / "training.py",
        models_dir / "evaluation.py",
        models_dir / "importance.py",
    ]
    offending = []
    for path in pure_logic_files:
        for module in _imported_modules(path):
            is_query_capable = (
                module.startswith("app.db.engine") or module.startswith("app.db.upsert")
            )
            is_sqlalchemy_import = module == "sqlalchemy" or module.startswith("sqlalchemy.")
            if is_query_capable or is_sqlalchemy_import:
                offending.append(f"{path}: imports {module}")
    assert offending == []
