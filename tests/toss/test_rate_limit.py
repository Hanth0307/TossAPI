from __future__ import annotations

from app.toss.rate_limit import GroupThrottle, RateLimitGroup


class _FakeMonotonicClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def test_first_call_in_a_group_never_waits() -> None:
    clock = _FakeMonotonicClock()
    sleeps: list[float] = []
    throttle = GroupThrottle(clock=clock, sleep_fn=sleeps.append)

    throttle.wait(RateLimitGroup.ACCOUNT)

    assert sleeps == []


def test_second_call_within_min_interval_sleeps_the_remainder() -> None:
    clock = _FakeMonotonicClock()
    sleeps: list[float] = []
    throttle = GroupThrottle(
        group_tps={RateLimitGroup.ACCOUNT: 1.0}, clock=clock, sleep_fn=sleeps.append
    )

    throttle.wait(RateLimitGroup.ACCOUNT)
    clock.value = 0.3  # only 0.3s elapsed, min interval is 1.0s
    throttle.wait(RateLimitGroup.ACCOUNT)

    assert sleeps == [0.7]


def test_call_after_min_interval_has_elapsed_does_not_sleep() -> None:
    clock = _FakeMonotonicClock()
    sleeps: list[float] = []
    throttle = GroupThrottle(
        group_tps={RateLimitGroup.ACCOUNT: 1.0}, clock=clock, sleep_fn=sleeps.append
    )

    throttle.wait(RateLimitGroup.ACCOUNT)
    clock.value = 5.0
    throttle.wait(RateLimitGroup.ACCOUNT)

    assert sleeps == []


def test_groups_are_paced_independently() -> None:
    clock = _FakeMonotonicClock()
    sleeps: list[float] = []
    throttle = GroupThrottle(
        group_tps={RateLimitGroup.ACCOUNT: 1.0, RateLimitGroup.STOCK: 5.0},
        clock=clock,
        sleep_fn=sleeps.append,
    )

    throttle.wait(RateLimitGroup.ACCOUNT)
    throttle.wait(RateLimitGroup.STOCK)  # different group, no wait expected

    assert sleeps == []


def test_zero_tps_disables_throttling() -> None:
    clock = _FakeMonotonicClock()
    sleeps: list[float] = []
    throttle = GroupThrottle(
        group_tps={RateLimitGroup.ACCOUNT: 0.0}, clock=clock, sleep_fn=sleeps.append
    )

    throttle.wait(RateLimitGroup.ACCOUNT)
    throttle.wait(RateLimitGroup.ACCOUNT)

    assert sleeps == []


def test_default_group_tps_matches_official_docs() -> None:
    throttle = GroupThrottle()
    assert throttle._tps[RateLimitGroup.AUTH] == 5.0
    assert throttle._tps[RateLimitGroup.ACCOUNT] == 1.0
    assert throttle._tps[RateLimitGroup.ASSET] == 5.0
    assert throttle._tps[RateLimitGroup.STOCK] == 5.0
