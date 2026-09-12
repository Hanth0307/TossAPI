"""Exercises `get_or_insert`'s concurrent-race recovery branch.

Genuinely reproducing the race (two sessions interleaved between the
lookup SELECT and the INSERT) needs real concurrency; this isolates
the recovery *logic* with a mocked `Session` instead, which is the
standard way to test an error-recovery branch that only fires under
timing that a single-threaded test cannot reliably force against a
real database.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from app.db.repositories._idempotent_insert import get_or_insert
from app.db.schema import model_runs


def test_integrity_error_during_insert_recovers_by_reselecting_the_winner() -> None:
    session = MagicMock()

    not_found = MagicMock()
    not_found.scalar_one_or_none.return_value = None
    found_after_race = MagicMock()
    found_after_race.scalar_one_or_none.return_value = 42

    session.execute.side_effect = [
        not_found,  # initial lookup: no existing row yet
        IntegrityError("insert ...", {}, Exception("duplicate key")),  # a concurrent winner beat us
        found_after_race,  # re-select after the race: the winner's row
    ]
    session.begin_nested.return_value.__enter__.return_value = None
    session.begin_nested.return_value.__exit__.return_value = False

    new_id, created = get_or_insert(
        session,
        model_runs,
        lookup={"idempotency_key": "race-key"},
        values={"idempotency_key": "race-key", "model_name": "x", "status": "running"},
    )

    assert new_id == 42
    assert created is False


def test_integrity_error_with_no_winner_found_reraises() -> None:
    """If the re-select still finds nothing, the IntegrityError was for
    a different reason entirely - it must propagate, not be swallowed.
    """
    session = MagicMock()

    not_found = MagicMock()
    not_found.scalar_one_or_none.return_value = None

    session.execute.side_effect = [
        not_found,
        IntegrityError("insert ...", {}, Exception("some other constraint")),
        not_found,
    ]
    session.begin_nested.return_value.__enter__.return_value = None
    session.begin_nested.return_value.__exit__.return_value = False

    try:
        get_or_insert(
            session,
            model_runs,
            lookup={"idempotency_key": "race-key"},
            values={"idempotency_key": "race-key", "model_name": "x", "status": "running"},
        )
        raise AssertionError("expected IntegrityError to propagate")
    except IntegrityError:
        pass
