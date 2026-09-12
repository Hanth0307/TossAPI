"""Minimal interval-based ingestion scheduler skeleton.

No cron/APScheduler dependency - a caller (a real cron trigger, a loop,
a test) calls `tick()` periodically; `tick()` runs every registered
job whose interval has elapsed since it last ran (or that has never
run) and returns which ones ran. Fake-clock injectable for
deterministic tests (`tests/ingest/test_scheduler.py`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class ScheduledJob:
    name: str
    interval_seconds: float
    fn: Callable[[], None]
    last_run_at: datetime | None = None


class IngestScheduler:
    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._jobs: dict[str, ScheduledJob] = {}

    def register_job(self, name: str, interval_seconds: float, fn: Callable[[], None]) -> None:
        if name in self._jobs:
            raise ValueError(f"job {name!r} is already registered")
        self._jobs[name] = ScheduledJob(name=name, interval_seconds=interval_seconds, fn=fn)

    def unregister_job(self, name: str) -> None:
        self._jobs.pop(name, None)

    def tick(self) -> list[str]:
        """Runs every due job once. Returns the names that ran, in
        registration order. A job raising does not stop the others -
        it propagates only after the rest of the tick has run, and its
        `last_run_at` is still updated (it "ran", even though it
        failed) so it does not immediately re-fire in a hot loop.
        """
        now = self._clock()
        ran: list[str] = []
        first_error: BaseException | None = None

        for job in self._jobs.values():
            due = (
                job.last_run_at is None
                or (now - job.last_run_at).total_seconds() >= job.interval_seconds
            )
            if not due:
                continue
            job.last_run_at = now
            ran.append(job.name)
            try:
                job.fn()
            except BaseException as exc:  # noqa: BLE001 - re-raised after the loop
                if first_error is None:
                    first_error = exc

        if first_error is not None:
            raise first_error
        return ran
