from __future__ import annotations

import pytest

from app.execution.base import ExecutionEngine


def test_execution_engine_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        ExecutionEngine()  # type: ignore[abstract]
