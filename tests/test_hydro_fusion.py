"""End-to-end: synthetic surge -> hydro detect -> channel -> fuse.

This is the path that must survive a refused DHM agreement (blocker B2): the loader is
swapped, everything downstream is unchanged. exp008 raised its importance — an
independent gauge channel is the only corroboration available for small events, which
are single-station by nature and so invisible to cross-station seismic agreement.
"""

from __future__ import annotations

from ghadi.fusion import Channel, Tier, channel_from_hydro, fuse
from ghadi.hydro import detect_anomaly, synthetic_surge


def _seismic(probability: float) -> Channel:
    return Channel(
        name="seismic",
        probability=probability,
        independence_group="upstream_seismic",
        detail="mass-movement classifier",
    )


def test_a_live_gauge_surge_becomes_a_corroborating_channel() -> None:
    times, stage = synthetic_surge()
    anomaly = detect_anomaly(times, stage)
    channel = channel_from_hydro(anomaly)

    assert anomaly.detected
    assert channel.alive
    assert channel.probability > 0.5
    assert channel.independence_group == "downstream_gauge"


def test_seismic_plus_gauge_reaches_warning_but_seismic_alone_does_not() -> None:
    """The corroboration requirement, exercised through the real hydro detector.

    A strong seismic detection alone is held below WARNING — one independent group.
    Adding an independent gauge anomaly is what earns the warning."""
    times, stage = synthetic_surge()
    gauge = channel_from_hydro(detect_anomaly(times, stage))

    seismic_only = fuse([_seismic(0.85)])
    corroborated = fuse([_seismic(0.85), gauge])

    assert seismic_only.tier is Tier.ADVISORY  # high p, but one group
    assert corroborated.tier is Tier.WARNING
    assert corroborated.independent_groups == 2


def test_a_gauge_that_died_before_the_surge_is_a_dead_channel_not_low_risk() -> None:
    """The confidently-wrong failure the architecture exists to prevent.

    A sensor destroyed before it saw anything cannot report absence. It must become a
    lost channel that fusion states, never a live channel reporting low risk — that is
    what four of five gauges did on 26 August 2026.
    """
    # Sensor destroyed at 300 s; the surge does not start rising until 1200 s. The
    # ingestion layer notices the gauge stopped reporting and passes sensor_alive=False.
    times, stage = synthetic_surge(surge_start_s=1200.0, destroy_at_s=300.0)
    anomaly = detect_anomaly(times, stage)
    channel = channel_from_hydro(anomaly, sensor_alive=False)

    assert not anomaly.detected
    assert not channel.alive, "a dead gauge must not present as a live low-risk channel"

    decision = fuse([_seismic(0.85), channel])
    assert "hydro" in decision.channels_dead
    assert decision.degraded
    assert "DEGRADED" in decision.degradation_note


def test_a_gauge_destroyed_by_the_surge_it_detected_stays_live() -> None:
    """The other truncation case: the sensor caught the rise, then died. That is a
    real detection and must count, truncation notwithstanding."""
    # Destroyed at 2400 s, after the 1200-3000 s rise is well under way. Even told the
    # sensor is now offline, a detection already recorded is evidence and stays live.
    times, stage = synthetic_surge(destroy_at_s=2400.0)
    anomaly = detect_anomaly(times, stage)
    channel = channel_from_hydro(anomaly, sensor_alive=False)

    assert anomaly.detected
    assert channel.alive, "a recorded detection is evidence regardless of later death"
    assert channel.probability > 0.5


def test_a_quiet_live_gauge_is_a_live_low_probability_channel() -> None:
    times, stage = synthetic_surge(surge_rise_m=0.0, noise_m=0.01)
    channel = channel_from_hydro(detect_anomaly(times, stage))
    assert channel.alive
    assert channel.probability < 0.2


def test_the_dead_gauge_and_a_quiet_gauge_are_not_confused() -> None:
    """Both are 'not detected', but one is alive and one is dead — and that
    distinction is the whole point. Same probability floor, opposite liveness."""
    quiet = channel_from_hydro(
        detect_anomaly(*synthetic_surge(surge_rise_m=0.0)), sensor_alive=True
    )
    dead = channel_from_hydro(
        detect_anomaly(*synthetic_surge(surge_start_s=1200.0, destroy_at_s=300.0)),
        sensor_alive=False,
    )
    assert quiet.alive and not dead.alive
    assert quiet.probability == dead.probability  # neither fabricates a distinction


def test_gauge_shares_an_independence_group_with_itself_not_the_seismic() -> None:
    """A duplicated gauge feed cannot manufacture corroboration; a gauge and a
    seismometer are genuinely independent and should reach WARNING together."""
    gauge = channel_from_hydro(detect_anomaly(*synthetic_surge()))
    gauge_dup = Channel(
        name="gauge_mirror",
        probability=gauge.probability,
        independence_group=gauge.independence_group,
    )
    # Two feeds off one gauge: still one group, held below WARNING.
    assert fuse([gauge, gauge_dup]).tier is not Tier.WARNING
