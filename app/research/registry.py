"""File-based Strategy Registry.

Stores each `StrategySpec` version as one JSON file under
`<base_dir>/<strategy_id>/<version>.json`, so research artifacts are
plain, diffable files that can be reviewed like any other change - no
database dependency for Phase 01 (see
docs/architecture/0006-strategy-research-lab.md).

Saving is append-only by default: an existing (strategy_id, version)
file is never silently overwritten, so a saved research result stays
reproducible. Nothing in this module talks to a broker, a risk
engine, or TradingView - it only reads and writes JSON files.
"""

from __future__ import annotations

from pathlib import Path

from app.core.exceptions import StrategyNotFoundError, StrategyVersionExistsError
from app.research.models import StrategySpec

DEFAULT_REGISTRY_DIR = Path("research/strategies")


class StrategyRegistry:
    """Reads and writes `StrategySpec` records under `base_dir`."""

    def __init__(self, base_dir: Path | str = DEFAULT_REGISTRY_DIR) -> None:
        self._base_dir = Path(base_dir)

    def save(self, spec: StrategySpec, *, overwrite: bool = False) -> Path:
        strategy_dir = self._base_dir / spec.strategy_id
        strategy_dir.mkdir(parents=True, exist_ok=True)
        path = strategy_dir / f"{spec.version}.json"

        if path.exists() and not overwrite:
            raise StrategyVersionExistsError(
                f"{spec.strategy_id} version {spec.version} already exists at {path}"
            )

        path.write_text(spec.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path

    def load(self, strategy_id: str, version: str) -> StrategySpec:
        path = self._base_dir / strategy_id / f"{version}.json"
        if not path.exists():
            raise StrategyNotFoundError(f"{strategy_id} version {version} not found at {path}")
        return StrategySpec.model_validate_json(path.read_text(encoding="utf-8"))

    def load_latest(self, strategy_id: str) -> StrategySpec:
        """Load the version with the most recent `created_at`.

        Version strings are free-form (not assumed to be semver), so
        "latest" is resolved by the recorded creation timestamp rather
        than by sorting version strings.
        """
        versions = self.list_versions(strategy_id)
        if not versions:
            raise StrategyNotFoundError(f"no versions found for {strategy_id}")
        specs = [self.load(strategy_id, version) for version in versions]
        return max(specs, key=lambda spec: spec.created_at)

    def list_versions(self, strategy_id: str) -> list[str]:
        strategy_dir = self._base_dir / strategy_id
        if not strategy_dir.exists():
            return []
        return sorted(path.stem for path in strategy_dir.glob("*.json"))

    def list_strategy_ids(self) -> list[str]:
        if not self._base_dir.exists():
            return []
        return sorted(path.name for path in self._base_dir.iterdir() if path.is_dir())
