"""Choosing which trigger in a window belongs to the event the window is labelled with.

**Why this module exists.** exp002 found that taking the first trigger is unsafe. On a
window cut around the 18 August 2026 M4.3 origin, the first trigger fired 276 seconds
*before* the catalogued origin time — an unrelated earlier transient — and the labelled
earthquake was the third of four triggers. Every feature computed from that onset
described the wrong arrival, correctly.

That matters well beyond one window. Issue 1.2 harvests a reference-earthquake corpus by
cutting windows around catalogue origin times, so without a rule here some fraction of
the corpus would be labelled for one event and measured on another — a silent label
error, which is the worst kind.

**The rule is causality.** A signal cannot arrive before the event that produced it.
Any trigger preceding the origin time is definitionally not this event, whatever else it
may be. Among the triggers that remain, the earliest one arriving within a plausible
travel-time window is the arrival being labelled.

This is a labelling tool for corpus construction, not a real-time detector: it requires
a catalogue origin time, which in operation is exactly what you do not have.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geo import p_travel_time_s
from .sta_lta import Trigger

# Slack around the predicted P arrival. Covers velocity-model error, depth, picking
# scatter and the fact that STA/LTA fires late on an emergent onset rather than at the
# true arrival.
DEFAULT_TOLERANCE_S = 90.0


@dataclass(frozen=True)
class OnsetPick:
    """Which trigger was chosen for a labelled event, and why."""

    trigger: Trigger | None
    onset_s: float | None
    reason: str
    n_rejected_before_origin: int
    n_candidates: int

    @property
    def ok(self) -> bool:
        return self.trigger is not None


def pick_onset(
    triggers: tuple[Trigger, ...] | list[Trigger],
    origin_offset_s: float,
    distance_km: float | None = None,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> OnsetPick:
    """Select the trigger corresponding to an event at ``origin_offset_s``.

    Args:
        triggers: triggers from a detector, in seconds from the window start.
        origin_offset_s: the catalogue origin time, in seconds from the window start.
        distance_km: epicentral distance, used to predict the P arrival. When None,
            any trigger after the origin is a candidate and the earliest wins.
        tolerance_s: slack either side of the predicted arrival.

    Returns:
        An OnsetPick that records what was chosen and what was discarded. A failure
        is a result, not an exception: a window where no trigger matches the labelled
        event is a fact about the corpus and must be counted, not skipped silently.
    """
    ordered = sorted(triggers, key=lambda t: t.on_s)

    # Causality: nothing arrives before its own origin.
    before = [t for t in ordered if t.on_s < origin_offset_s]
    after = [t for t in ordered if t.on_s >= origin_offset_s]

    if not after:
        return OnsetPick(
            trigger=None,
            onset_s=None,
            reason=(
                f"no trigger at or after the origin (+{origin_offset_s:.0f}s); "
                f"{len(before)} trigger(s) precede it and cannot be this event"
            ),
            n_rejected_before_origin=len(before),
            n_candidates=0,
        )

    if distance_km is None:
        chosen = after[0]
        return OnsetPick(
            trigger=chosen,
            onset_s=chosen.on_s,
            reason=(
                f"earliest trigger after the origin; {len(before)} earlier "
                "trigger(s) rejected as pre-origin"
            ),
            n_rejected_before_origin=len(before),
            n_candidates=len(after),
        )

    predicted = origin_offset_s + p_travel_time_s(distance_km)
    window = [t for t in after if abs(t.on_s - predicted) <= tolerance_s]
    if not window:
        return OnsetPick(
            trigger=None,
            onset_s=None,
            reason=(
                f"no trigger within {tolerance_s:.0f}s of the predicted P arrival "
                f"(+{predicted:.0f}s) at {distance_km:.0f} km; "
                f"{len(after)} post-origin trigger(s) all fell outside it"
            ),
            n_rejected_before_origin=len(before),
            n_candidates=len(after),
        )

    chosen = min(window, key=lambda t: abs(t.on_s - predicted))
    return OnsetPick(
        trigger=chosen,
        onset_s=chosen.on_s,
        reason=(
            f"closest to the predicted P arrival (+{predicted:.0f}s at "
            f"{distance_km:.0f} km); {len(before)} pre-origin trigger(s) rejected"
        ),
        n_rejected_before_origin=len(before),
        n_candidates=len(after),
    )
