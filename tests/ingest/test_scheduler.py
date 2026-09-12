"""Pure logic - no database needed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.ingest.scheduler import IngestScheduler


class _FakeClock:
    def __init__(self, start: datetime) -> None:
        self._now = start

    def __call__(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)


def test_a_new_job_runs_on_the_first_tick() -> None:
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    scheduler = IngestScheduler(clock=clock)
    calls = []
    scheduler.register_job("job-a", interval_seconds=60, fn=lambda: calls.append("ran"))

    ran = scheduler.tick()

    assert ran == ["job-a"]
    assert calls == ["ran"]


def test_a_job_does_not_rerun_before_its_interval_elapses() -> None:
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    scheduler = IngestScheduler(clock=clock)
    calls = []
    scheduler.register_job("job-a", interval_seconds=60, fn=lambda: calls.append("ran"))

    scheduler.tick()
    clock.advance(30)
    ran = scheduler.tick()

    assert ran == []
    assert calls == ["ran"]


def test_a_job_reruns_once_its_interval_has_elapsed() -> None:
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    scheduler = IngestScheduler(clock=clock)
    calls = []
    scheduler.register_job("job-a", interval_seconds=60, fn=lambda: calls.append("ran"))

    scheduler.tick()
    clock.advance(61)
    ran = scheduler.tick()

    assert ran == ["job-a"]
    assert calls == ["ran", "ran"]


def test_multiple_jobs_are_paced_independently() -> None:
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    scheduler = IngestScheduler(clock=clock)
    calls: list[str] = []
    scheduler.register_job("fast", interval_seconds=10, fn=lambda: calls.append("fast"))
    scheduler.register_job("slow", interval_seconds=100, fn=lambda: calls.append("slow"))

    scheduler.tick()  # both run
    clock.advance(15)
    ran = scheduler.tick()  # only fast is due

    assert ran == ["fast"]
    assert calls == ["fast", "slow", "fast"]


def test_unregister_job_stops_it_from_running() -> None:
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    scheduler = IngestScheduler(clock=clock)
    calls: list[str] = []
    scheduler.register_job("job-a", interval_seconds=60, fn=lambda: calls.append("ran"))

    scheduler.unregister_job("job-a")
    ran = scheduler.tick()

    assert ran == []
    assert calls == []


def test_registering_the_same_job_name_twice_raises() -> None:
    scheduler = IngestScheduler()
    scheduler.register_job("job-a", interval_seconds=60, fn=lambda: None)
    with pytest.raises(ValueError, match="job-a"):
        scheduler.register_job("job-a", interval_seconds=60, fn=lambda: None)


def test_a_failing_job_still_lets_other_due_jobs_run_this_tick() -> None:
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    scheduler = IngestScheduler(clock=clock)
    calls: list[str] = []

    def _boom() -> None:
        raise RuntimeError("simulated ingestion failure")

    scheduler.register_job("broken", interval_seconds=60, fn=_boom)
    scheduler.register_job("healthy", interval_seconds=60, fn=lambda: calls.append("healthy"))

    with pytest.raises(RuntimeError, match="simulated ingestion failure"):
        scheduler.tick()

    assert calls == ["healthy"]


def test_a_failed_job_does_not_immediately_rerun_next_tick() -> None:
    """Its last_run_at was still recorded, so it will not hot-loop."""
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    scheduler = IngestScheduler(clock=clock)
    attempts = {"count": 0}

    def _boom() -> None:
        attempts["count"] += 1
        raise RuntimeError("fail")

    scheduler.register_job("broken", interval_seconds=60, fn=_boom)

    with pytest.raises(RuntimeError):
        scheduler.tick()
    assert attempts["count"] == 1

    clock.advance(1)
    ran = scheduler.tick()
    assert ran == []
    assert attempts["count"] == 1
