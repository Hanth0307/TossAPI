"""Statically proves the Phase 03 module boundary: `app.db` has no
import edge to `app.toss`, `app.research`, `app.ingest`, `app.brokers`,
`app.risk`, or `app.execution` - and that adding `app.db`/`app.ingest`
did not accidentally create a reverse dependency from `app.research`
or `app.toss` (whose own isolation was established in Phase 01/02).
See docs/architecture/0001-module-boundaries.md and
docs/architecture/0008-data-platform.md.
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


def _assert_no_forbidden_imports(package_dir: Path, forbidden_prefixes: tuple[str, ...]) -> None:
    offending: list[str] = []
    for path in package_dir.rglob("*.py"):
        for module in _imported_modules(path):
            if module.startswith(forbidden_prefixes):
                offending.append(f"{path}: imports {module}")
    assert offending == []


def test_app_db_has_no_import_edge_to_toss_research_ingest_or_execution_packages() -> None:
    _assert_no_forbidden_imports(
        REPO_ROOT / "app" / "db",
        ("app.toss", "app.research", "app.ingest", "app.brokers", "app.risk", "app.execution"),
    )


def test_app_research_still_has_no_import_edge_to_db_or_ingest() -> None:
    _assert_no_forbidden_imports(REPO_ROOT / "app" / "research", ("app.db", "app.ingest"))


def test_app_toss_still_has_no_import_edge_to_db_or_ingest() -> None:
    _assert_no_forbidden_imports(REPO_ROOT / "app" / "toss", ("app.db", "app.ingest"))
