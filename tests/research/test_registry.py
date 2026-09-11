from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.core.exceptions import StrategyNotFoundError, StrategyVersionExistsError
from app.research.models import StrategySource, StrategySpec
from app.research.registry import StrategyRegistry


def _spec(version: str, created_at: datetime | None = None) -> StrategySpec:
    kwargs: dict[str, Any] = dict(
        strategy_id="STR-TEST-001",
        name="Test strategy",
        version=version,
        source=StrategySource.MANUAL,
        hypothesis="Placeholder hypothesis.",
        universe=["KOSPI:005930"],
        timeframe="1D",
        entry_rules=["rule"],
        exit_rules=["rule"],
        risk_assumptions=["assumption"],
    )
    if created_at is not None:
        kwargs["created_at"] = created_at
    return StrategySpec(**kwargs)


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    registry = StrategyRegistry(base_dir=tmp_path)
    spec = _spec("0.1.0")

    path = registry.save(spec)

    assert path.exists()
    reloaded = registry.load(spec.strategy_id, spec.version)
    assert reloaded == spec


def test_save_rejects_duplicate_version_without_overwrite(tmp_path: Path) -> None:
    registry = StrategyRegistry(base_dir=tmp_path)
    spec = _spec("0.1.0")
    registry.save(spec)

    with pytest.raises(StrategyVersionExistsError):
        registry.save(spec)


def test_save_allows_overwrite_when_requested(tmp_path: Path) -> None:
    registry = StrategyRegistry(base_dir=tmp_path)
    spec = _spec("0.1.0")
    registry.save(spec)

    registry.save(spec, overwrite=True)  # must not raise


def test_load_missing_version_raises_not_found(tmp_path: Path) -> None:
    registry = StrategyRegistry(base_dir=tmp_path)
    with pytest.raises(StrategyNotFoundError):
        registry.load("STR-DOES-NOT-EXIST", "0.1.0")


def test_load_latest_picks_most_recent_created_at(tmp_path: Path) -> None:
    registry = StrategyRegistry(base_dir=tmp_path)
    older = _spec("0.1.0", created_at=datetime(2023, 1, 1, tzinfo=UTC))
    newer = _spec("0.2.0", created_at=datetime(2023, 6, 1, tzinfo=UTC))
    registry.save(older)
    registry.save(newer)

    latest = registry.load_latest("STR-TEST-001")

    assert latest.version == "0.2.0"


def test_load_latest_raises_when_no_versions_exist(tmp_path: Path) -> None:
    registry = StrategyRegistry(base_dir=tmp_path)
    with pytest.raises(StrategyNotFoundError):
        registry.load_latest("STR-UNKNOWN")


def test_list_versions_and_strategy_ids(tmp_path: Path) -> None:
    registry = StrategyRegistry(base_dir=tmp_path)
    registry.save(_spec("0.1.0"))
    registry.save(_spec("0.2.0"))

    assert registry.list_versions("STR-TEST-001") == ["0.1.0", "0.2.0"]
    assert registry.list_strategy_ids() == ["STR-TEST-001"]


def test_list_versions_for_unknown_strategy_is_empty(tmp_path: Path) -> None:
    registry = StrategyRegistry(base_dir=tmp_path)
    assert registry.list_versions("STR-UNKNOWN") == []


def test_list_strategy_ids_for_empty_registry_is_empty(tmp_path: Path) -> None:
    registry = StrategyRegistry(base_dir=tmp_path / "does-not-exist-yet")
    assert registry.list_strategy_ids() == []
