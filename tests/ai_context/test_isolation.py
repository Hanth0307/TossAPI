"""Statically proves the Phase 05 `app.ai_context` module boundary: no
import edge to `app.toss`, `app.research`, `app.ingest`, `app.brokers`,
`app.risk`, or `app.execution`, and only `persistence.py` touches
`app.db`/`sqlalchemy` - `schema.py`/`extractor.py`/
`mock_extractor.py`/`claude_extractor.py` are pure logic (the LLM call
itself is an isolated network boundary, not a database one).
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


def test_app_ai_context_has_no_import_edge_to_forbidden_packages() -> None:
    forbidden = (
        "app.toss", "app.research", "app.ingest", "app.brokers", "app.risk", "app.execution",
    )
    offending = []
    for path in (REPO_ROOT / "app" / "ai_context").rglob("*.py"):
        for module in _imported_modules(path):
            if module.startswith(forbidden):
                offending.append(f"{path}: imports {module}")
    assert offending == []


def test_app_ai_context_pure_logic_modules_have_no_database_import() -> None:
    ai_context_dir = REPO_ROOT / "app" / "ai_context"
    pure_logic_files = [
        ai_context_dir / "schema.py",
        ai_context_dir / "extractor.py",
        ai_context_dir / "mock_extractor.py",
        ai_context_dir / "claude_extractor.py",
    ]
    offending = []
    for path in pure_logic_files:
        for module in _imported_modules(path):
            is_db_import = module.startswith("app.db")
            is_sqlalchemy_import = module == "sqlalchemy" or module.startswith("sqlalchemy.")
            if is_db_import or is_sqlalchemy_import:
                offending.append(f"{path}: imports {module}")
    assert offending == []
