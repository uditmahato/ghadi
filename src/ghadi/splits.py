"""Train/test splitting — the part most disaster-ML work gets wrong (issue 1.4).

Three rules, to be stated in every paper and enforced here rather than in good
intentions (HANDOFF §6.4):

1. **Event holdout.** Hold out entire events. A model that has seen half the 26 August
   window will trivially classify the other half.
2. **Temporal holdout.** Train on the past, test on the future, because that is the
   deployment condition.
3. **Station-configuration holdout.** Evaluate with stations removed. One-station
   operation is the normal case in Nepal, not the degraded case.

**Random windowed splits are forbidden.** They will produce a beautiful, meaningless
number, because adjacent windows from one event are not independent samples.
``assert_no_random_split`` exists so that a reviewer can point at a line of code
rather than at a paragraph of intent, and ``tests/test_splits.py`` fails if the
guard is removed.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class Sample(Protocol):
    """The minimum a record must expose to be split correctly."""

    @property
    def event_id(self) -> str: ...

    @property
    def time_utc(self) -> datetime: ...


@dataclass(frozen=True)
class Split:
    train: tuple[int, ...]  # indices into the input sequence
    test: tuple[int, ...]
    policy: str
    rationale: str

    def __post_init__(self) -> None:
        overlap = set(self.train) & set(self.test)
        if overlap:
            raise ValueError(f"train and test overlap on {len(overlap)} sample(s)")


class SplitPolicyError(ValueError):
    """A split violated the policy."""


def assert_no_random_split(train_events: Iterable[str], test_events: Iterable[str]) -> None:
    """Fail if any event appears on both sides of a split.

    This is the check that random windowed splitting cannot pass, and it is the
    reason the split functions return indices rather than shuffled data.
    """
    shared = set(train_events) & set(test_events)
    if shared:
        raise SplitPolicyError(
            f"{len(shared)} event(s) appear in both train and test "
            f"(e.g. {sorted(shared)[:3]}). Hold out whole events — a model that has "
            "seen part of an event will trivially classify the rest."
        )


def event_holdout(samples: Sequence[Sample], test_event_ids: Iterable[str]) -> Split:
    """Hold out every window belonging to the named events."""
    held = set(test_event_ids)
    train = tuple(i for i, s in enumerate(samples) if s.event_id not in held)
    test = tuple(i for i, s in enumerate(samples) if s.event_id in held)

    assert_no_random_split(
        (samples[i].event_id for i in train), (samples[i].event_id for i in test)
    )
    return Split(
        train=train,
        test=test,
        policy="event_holdout",
        rationale=f"held out {len(held)} event(s) entirely: {sorted(held)}",
    )


def temporal_holdout(samples: Sequence[Sample], cutoff_utc: datetime) -> Split:
    """Train on everything before the cutoff, test on everything after.

    This is the deployment condition: a model in operation has only ever seen the
    past. Where the temporal result diverges sharply from an event-holdout result,
    the temporal one is the honest estimate.
    """
    if cutoff_utc.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware (HANDOFF §5.3)")

    train = tuple(i for i, s in enumerate(samples) if s.time_utc < cutoff_utc)
    test = tuple(i for i, s in enumerate(samples) if s.time_utc >= cutoff_utc)

    # An event straddling the cutoff would leak across it.
    assert_no_random_split(
        (samples[i].event_id for i in train), (samples[i].event_id for i in test)
    )
    return Split(
        train=train,
        test=test,
        policy="temporal_holdout",
        rationale=f"train < {cutoff_utc.isoformat()} <= test",
    )


def leave_one_event_out(samples: Sequence[Sample]) -> list[Split]:
    """One fold per event. Report per-event performance, never pooled.

    With very few positive events, a pooled metric can be carried entirely by one
    well-recorded example while the model fails on every other — which is precisely
    the failure mode a project with a handful of large cascades has to guard against.
    """
    event_ids = sorted({s.event_id for s in samples})
    return [event_holdout(samples, [event_id]) for event_id in event_ids]
