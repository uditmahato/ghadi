"""Split policy (issue 1.4). Tests that fail on random splitting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from ghadi.splits import (
    SplitPolicyError,
    assert_no_random_split,
    event_holdout,
    leave_one_event_out,
    temporal_holdout,
)


@dataclass(frozen=True)
class Window:
    event_id: str
    time_utc: datetime


def windows() -> list[Window]:
    """Three events, several windows each — the shape that makes random splits lie."""
    return [
        Window("EV-A", datetime(2024, 1, 1, tzinfo=UTC)),
        Window("EV-A", datetime(2024, 1, 1, 0, 5, tzinfo=UTC)),
        Window("EV-A", datetime(2024, 1, 1, 0, 10, tzinfo=UTC)),
        Window("EV-B", datetime(2025, 6, 1, tzinfo=UTC)),
        Window("EV-B", datetime(2025, 6, 1, 0, 5, tzinfo=UTC)),
        Window("EV-C", datetime(2026, 8, 26, tzinfo=UTC)),
    ]


def test_event_holdout_keeps_every_window_of_an_event_together() -> None:
    split = event_holdout(windows(), ["EV-A"])
    assert set(split.test) == {0, 1, 2}
    assert set(split.train) == {3, 4, 5}


def test_a_random_split_is_rejected() -> None:
    """The guard that makes the policy enforceable rather than aspirational.

    Splitting windows at random puts windows from one event on both sides. The model
    then scores well by recognising the event it already saw, and the number is
    meaningless.
    """
    samples = windows()
    train_ids = [samples[i].event_id for i in (0, 1, 3, 5)]
    test_ids = [samples[i].event_id for i in (2, 4)]  # EV-A and EV-B on both sides
    with pytest.raises(SplitPolicyError, match="both train and test"):
        assert_no_random_split(train_ids, test_ids)


def test_temporal_holdout_trains_on_the_past() -> None:
    split = temporal_holdout(windows(), datetime(2026, 1, 1, tzinfo=UTC))
    assert set(split.test) == {5}
    assert set(split.train) == {0, 1, 2, 3, 4}


def test_temporal_cutoff_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        temporal_holdout(windows(), datetime(2026, 1, 1))


def test_a_cutoff_that_splits_an_event_is_rejected() -> None:
    """An event straddling the cutoff leaks across it, which is the same failure as
    a random split wearing a temporal disguise."""
    with pytest.raises(SplitPolicyError):
        temporal_holdout(windows(), datetime(2024, 1, 1, 0, 7, tzinfo=UTC))


def test_leave_one_event_out_produces_one_fold_per_event() -> None:
    folds = leave_one_event_out(windows())
    assert len(folds) == 3
    for fold in folds:
        assert fold.test
        assert not set(fold.train) & set(fold.test)


def test_a_split_cannot_be_constructed_with_overlap() -> None:
    from ghadi.splits import Split

    with pytest.raises(ValueError, match="overlap"):
        Split(train=(0, 1), test=(1, 2), policy="bad", rationale="deliberate overlap")
