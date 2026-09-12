"""Statically proves the Phase 04 module boundary: `app.scanners` has
no import edge to `app.toss`, `app.research`, `app.ingest`,
`app.brokers`, `app.risk`, or `app.execution` - it reads exclusively
through `app.db.repositories`. See `app/scanners/__init__.py` and
docs/architecture/0010-scanner-pipeline.md.
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


def test_app_scanners_has_no_import_edge_to_toss_research_ingest_or_execution_packages() -> None:
    _assert_no_forbidden_imports(
        REPO_ROOT / "app" / "scanners",
        ("app.toss", "app.research", "app.ingest", "app.brokers", "app.risk", "app.execution"),
    )


def test_app_scanners_pure_logic_modules_have_no_import_edge_to_db() -> None:
    """`universe.py`/`events.py`/`strategy_rules.py`/`candidate.py` are
    pure logic over already-fetched data - only `pipeline.py`/
    `persistence.py` may touch `app.db` (see `app/scanners/__init__.py`).
    """
    scanners_dir = REPO_ROOT / "app" / "scanners"
    pure_logic_files = [
        scanners_dir / "universe.py",
        scanners_dir / "events.py",
        scanners_dir / "strategy_rules.py",
        scanners_dir / "candidate.py",
        scanners_dir / "features.py",
    ]
    offending: list[str] = []
    for path in pure_logic_files:
        for module in _imported_modules(path):
            if module.startswith("app.db.engine") or module.startswith("app.db.upsert"):
                offending.append(f"{path}: imports {module}")
            if module == "sqlalchemy" or module.startswith("sqlalchemy."):
                offending.append(f"{path}: imports {module}")
    assert offending == []
