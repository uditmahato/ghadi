"""Onset picking for labelled corpus windows (exp002's data-quality finding)."""

from __future__ import annotations

from ghadi.detect import Trigger, pick_onset
from ghadi.geo import haversine_km, p_travel_time_s, s_travel_time_s


def trig(on_s: float, peak: float = 10.0) -> Trigger:
    return Trigger(on_s=on_s, off_s=on_s + 20.0, peak_ratio=peak)


def test_a_trigger_before_the_origin_is_rejected() -> None:
    """The exp002 M4.3 case: the first trigger fired 276 s before the catalogued
    origin. A signal cannot arrive before the event that produced it, so whatever
    that transient was, it was not this earthquake."""
    pick = pick_onset([trig(324.3), trig(615.8)], origin_offset_s=600.0)
    assert pick.ok
    assert pick.onset_s == 615.8
    assert pick.n_rejected_before_origin == 1


def test_the_earliest_post_origin_trigger_wins_without_a_distance() -> None:
    pick = pick_onset([trig(700.0), trig(650.0), trig(900.0)], origin_offset_s=600.0)
    assert pick.onset_s == 650.0
    assert pick.n_candidates == 3


def test_distance_selects_the_trigger_nearest_the_predicted_arrival() -> None:
    # 300 km => P at ~50 s after origin. The 652 s trigger matches; 900 s does not.
    pick = pick_onset([trig(652.0), trig(900.0)], origin_offset_s=600.0, distance_km=300.0)
    assert pick.onset_s == 652.0
    assert "predicted P arrival" in pick.reason


def test_no_trigger_after_the_origin_is_a_recorded_failure_not_an_exception() -> None:
    """A window where nothing matches the labelled event is a fact about the corpus.
    It has to be counted, not skipped silently, or the corpus quietly shrinks."""
    pick = pick_onset([trig(100.0), trig(300.0)], origin_offset_s=600.0)
    assert not pick.ok
    assert pick.onset_s is None
    assert pick.n_rejected_before_origin == 2
    assert "cannot be this event" in pick.reason


def test_a_trigger_far_from_the_predicted_arrival_is_rejected() -> None:
    # 100 km => P at ~17 s. A trigger 500 s later is not this event's P arrival.
    pick = pick_onset([trig(1100.0)], origin_offset_s=600.0, distance_km=100.0)
    assert not pick.ok
    assert "predicted P arrival" in pick.reason


def test_empty_trigger_list_fails_cleanly() -> None:
    pick = pick_onset([], origin_offset_s=600.0)
    assert not pick.ok
    assert pick.n_candidates == 0


# --- geodesy ------------------------------------------------------------------------


def test_distance_to_the_2026_source_matches_the_handoff() -> None:
    """HANDOFF Appendix B gives 55.9 km from NK.KKN to the 2026 source zone."""
    distance = haversine_km(27.800, 85.279, 28.255, 85.520)
    assert 54.0 < distance < 58.0


def test_s_arrives_after_p() -> None:
    assert s_travel_time_s(300.0) > p_travel_time_s(300.0)


def test_s_minus_p_grows_with_distance() -> None:
    """The contamination exp002 identified: S-P scales with distance, so any feature
    measuring onset-to-peak inherits distance unless it is controlled for."""
    near = s_travel_time_s(50.0) - p_travel_time_s(50.0)
    far = s_travel_time_s(400.0) - p_travel_time_s(400.0)
    assert far > near * 5
