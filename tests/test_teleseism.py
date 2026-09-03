"""Teleseism suppression (exp004).

The two false alarms that motivated this module are used as the primary test cases,
with their real catalogue parameters, so the test fails if the physics stops working
rather than only if the code stops running.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ghadi.teleseism import (
    DEFAULT_MIN_MAGNITUDE,
    Origin,
    epicentral_distance_deg,
    explain,
    p_travel_time_s,
    surface_wave_travel_time_s,
)

STA_LAT, STA_LON = 27.800, 85.279  # NK.KKN

# Real events from exp004's false alarms.
BONIN = Origin(
    time_utc=datetime(2024, 7, 7, 20, 1, tzinfo=UTC),
    latitude=27.9,
    longitude=140.6,
    magnitude=6.2,
    place="Bonin Islands, Japan region",
)
INDONESIA = Origin(
    time_utc=datetime(2024, 9, 23, 19, 51, 2, tzinfo=UTC),
    latitude=-0.05,
    longitude=122.89,
    magnitude=6.0,
    place="67 km SSW of Gorontalo, Indonesia",
)


def test_travel_time_increases_with_distance_and_flattens() -> None:
    assert p_travel_time_s(10) < p_travel_time_s(40) < p_travel_time_s(90)
    # Beyond the table the curve is nearly flat, not linear.
    assert p_travel_time_s(120) == pytest.approx(p_travel_time_s(100))


def test_distance_to_bonin_is_teleseismic() -> None:
    d = epicentral_distance_deg(STA_LAT, STA_LON, BONIN)
    assert 40 < d < 55, f"expected ~47 deg, got {d:.1f}"


def test_the_bonin_false_alarm_is_suppressed() -> None:
    """exp004: this window's LF/HF was 19.2, far beyond the cascade's 4.14, and it was
    an M6.2 arriving from 47 degrees away."""
    distance = epicentral_distance_deg(STA_LAT, STA_LON, BONIN)
    arrival = BONIN.time_utc + timedelta(seconds=p_travel_time_s(distance))
    result = explain(arrival, [BONIN], STA_LAT, STA_LON)
    assert result.suppressed
    assert result.origin is BONIN
    assert "M6.2" in result.reason


def test_the_indonesia_false_alarm_is_suppressed() -> None:
    distance = epicentral_distance_deg(STA_LAT, STA_LON, INDONESIA)
    arrival = INDONESIA.time_utc + timedelta(seconds=p_travel_time_s(distance))
    result = explain(arrival, [INDONESIA], STA_LAT, STA_LON)
    assert result.suppressed


def test_a_local_event_is_not_suppressed_by_a_distant_one() -> None:
    """The failure that would matter: suppressing a real local mass movement because
    an unrelated earthquake happened somewhere else. Two hours later is well past even
    the slow surface train."""
    detection = BONIN.time_utc + timedelta(hours=2)
    result = explain(detection, [BONIN], STA_LAT, STA_LON)
    assert not result.suppressed
    assert "no catalogued" in result.reason


def test_a_trigger_on_the_lg_phase_is_suppressed() -> None:
    """exp006's regression case, and the reason the rule is a phase window.

    The M6.0 Indonesia trigger fired 647 s after the predicted P — and 24 s after the
    Lg/S arrival. STA/LTA fires on the largest arrival, which for a distant earthquake
    is S, Lg or the surface train, never P. A P-only tolerance missed it entirely.
    """
    distance = epicentral_distance_deg(STA_LAT, STA_LON, INDONESIA)
    p_time = p_travel_time_s(distance)
    lg_time = distance * 111.195 / 4.5  # Lg travels at roughly 4.5 km/s
    assert lg_time > p_time + 500, "test premise: Lg is far later than P here"

    detection = INDONESIA.time_utc + timedelta(seconds=lg_time)
    result = explain(detection, [INDONESIA], STA_LAT, STA_LON)
    assert result.suppressed, "a trigger on the Lg phase must still be attributed"


def test_the_window_closes_after_the_slow_surface_train() -> None:
    distance = epicentral_distance_deg(STA_LAT, STA_LON, INDONESIA)
    surface = surface_wave_travel_time_s(distance)
    assert surface > p_travel_time_s(distance)
    # Well past the surface train plus its margin, nothing is attributed.
    late = INDONESIA.time_utc + timedelta(seconds=surface + 3600)
    assert not explain(late, [INDONESIA], STA_LAT, STA_LON).suppressed


def test_small_earthquakes_do_not_suppress() -> None:
    """Below the magnitude floor a teleseism cannot trip a regional station, and
    suppressing on it would start hiding real local events."""
    small = Origin(
        time_utc=BONIN.time_utc,
        latitude=BONIN.latitude,
        longitude=BONIN.longitude,
        magnitude=DEFAULT_MIN_MAGNITUDE - 0.5,
    )
    distance = epicentral_distance_deg(STA_LAT, STA_LON, small)
    arrival = small.time_utc + timedelta(seconds=p_travel_time_s(distance))
    assert not explain(arrival, [small], STA_LAT, STA_LON).suppressed


def test_the_closest_matching_origin_wins() -> None:
    distance = epicentral_distance_deg(STA_LAT, STA_LON, BONIN)
    arrival = BONIN.time_utc + timedelta(seconds=p_travel_time_s(distance))
    decoy = Origin(
        time_utc=BONIN.time_utc + timedelta(seconds=90),
        latitude=BONIN.latitude,
        longitude=BONIN.longitude,
        magnitude=6.0,
        place="decoy",
    )
    result = explain(arrival, [decoy, BONIN], STA_LAT, STA_LON)
    assert result.origin is BONIN


def test_empty_catalogue_suppresses_nothing() -> None:
    result = explain(datetime(2026, 1, 1, tzinfo=UTC), [], STA_LAT, STA_LON)
    assert not result.suppressed
    assert result.origin is None


def test_naive_datetime_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        explain(datetime(2026, 1, 1), [BONIN], STA_LAT, STA_LON)


def test_suppression_always_carries_a_reason() -> None:
    """An alert suppressed without a stated reason is indistinguishable from one that
    was never raised, and the audit log has to tell those apart."""
    distance = epicentral_distance_deg(STA_LAT, STA_LON, BONIN)
    arrival = BONIN.time_utc + timedelta(seconds=p_travel_time_s(distance))
    for result in (
        explain(arrival, [BONIN], STA_LAT, STA_LON),
        explain(arrival + timedelta(hours=5), [BONIN], STA_LAT, STA_LON),
    ):
        assert result.reason


# --- the assertion that must never be assumed ---------------------------------------


def test_suppression_does_not_eat_the_target_event() -> None:
    """The 26 August 2026 cascade must survive teleseism suppression.

    Verified against the full committed global catalogue (1,133 origins at M>=5.5):
    none has a P-to-surface window containing the cascade's measured trigger onset.

    This is the failure that would be worst and quietest — a suppressor that removes
    the one event the project exists to detect, while every false-alarm metric
    improves. It is asserted, never assumed.
    """
    import json
    from pathlib import Path

    catalogue = Path(__file__).resolve().parents[1] / "data" / "corpus" / "global_catalogue.json"
    if not catalogue.exists():  # pragma: no cover - corpus not fetched
        pytest.skip("global catalogue not harvested")

    origins = [
        Origin(
            time_utc=datetime.fromisoformat(o["time_utc"]),
            latitude=o["latitude"],
            longitude=o["longitude"],
            magnitude=o["magnitude"],
            place=o.get("place", ""),
        )
        for o in json.loads(catalogue.read_text(encoding="utf-8"))["origins"]
    ]
    assert len(origins) > 500, "catalogue looks truncated; the assertion would be weak"

    cascade_onset = datetime(2026, 8, 26, 2, 52, 30, 320000, tzinfo=UTC)
    verdict = explain(cascade_onset, origins, STA_LAT, STA_LON)
    assert not verdict.suppressed, (
        f"teleseism suppression would have removed the 26 Aug 2026 cascade: {verdict.reason}"
    )
