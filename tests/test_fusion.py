"""Fusion: independence grouping, and degradation that is never silent."""

from __future__ import annotations

import pytest

from ghadi.fusion import Channel, Tier, fuse


def seismic(p: float = 0.9, alive: bool = True) -> Channel:
    return Channel("seismic_kkn", p, independence_group="seismic", alive=alive)


def gauge(p: float = 0.85, alive: bool = True, name: str = "gauge_timure") -> Channel:
    return Channel(name, p, independence_group="hydro", alive=alive)


def test_probability_must_be_a_probability() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        Channel("bad", 1.4, independence_group="seismic")


def test_two_independent_channels_reach_warning() -> None:
    decision = fuse([seismic(), gauge()])
    assert decision.tier is Tier.WARNING
    assert decision.independent_groups == 2
    assert not decision.degraded


def test_duplicated_feed_cannot_manufacture_corroboration() -> None:
    """Two channels fed by the same sensor are one channel (HANDOFF §4 rule 3)."""
    duplicated = fuse(
        [
            seismic(0.9),
            Channel("seismic_kkn_mirror", 0.9, independence_group="seismic"),
        ]
    )
    assert duplicated.independent_groups == 1
    assert duplicated.tier is not Tier.WARNING, (
        "a mirrored feed must not clear the corroboration requirement"
    )


def test_single_strong_seismic_channel_is_held_below_warning() -> None:
    decision = fuse([seismic(0.99)])
    assert decision.independent_groups == 1
    assert decision.tier is Tier.ADVISORY
    assert "corroboration requirement not met" in decision.rationale


def test_tier_degrades_rather_than_the_system_failing_silently() -> None:
    """Issue 4.2: under 1-, 2- and 3-channel loss the tier degrades and says so."""
    full = fuse([seismic(), gauge(), gauge(0.8, name="gauge_syabrubesi")])
    assert full.tier is Tier.WARNING
    assert not full.degraded

    one_lost = fuse([seismic(), gauge(alive=False), gauge(0.8, name="gauge_syabrubesi")])
    assert one_lost.degraded
    assert "DEGRADED" in one_lost.degradation_note
    assert "gauge_timure" in one_lost.degradation_note

    all_hydro_lost = fuse(
        [seismic(), gauge(alive=False), gauge(0.8, name="gauge_syabrubesi", alive=False)]
    )
    assert all_hydro_lost.tier is Tier.ADVISORY  # dropped from WARNING, not silently held
    assert all_hydro_lost.independent_groups == 1
    assert len(all_hydro_lost.channels_dead) == 2


def test_total_blindness_is_stated_not_scored_as_zero_risk() -> None:
    decision = fuse([seismic(alive=False), gauge(alive=False)])
    assert decision.tier is Tier.NONE
    assert decision.degraded
    assert "blind" in decision.rationale
    assert decision.channels_alive == ()


def test_weak_evidence_lands_in_watch() -> None:
    decision = fuse([Channel("seismic_kkn", 0.25, independence_group="seismic")])
    assert decision.tier is Tier.WATCH


def test_every_decision_states_its_channel_health() -> None:
    for decision in (fuse([seismic(), gauge()]), fuse([seismic(), gauge(alive=False)])):
        note = decision.degradation_note
        assert note and ("All" in note or "DEGRADED" in note)
