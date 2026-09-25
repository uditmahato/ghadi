"""Issue #31: two picks constrain where a source can be, and the test says how much."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from ghadi.associate import Pick, SearchRegion, arrival_bracket, associate, feasible_grid
from ghadi.geo import haversine_km

KKN = (27.800, 85.279)
EVN = (27.9592, 86.8133)
ZONE = (28.255, 85.520)
REGION = SearchRegion(27.4, 29.0, 84.6, 86.6, step_km=5.0)
T0 = datetime(2026, 8, 26, 2, 52, 24, tzinfo=UTC)


def picks_for_source(lat: float, lon: float, v: float) -> tuple[Pick, Pick]:
    d1 = haversine_km(lat, lon, *KKN)
    d2 = haversine_km(lat, lon, *EVN)
    first = Pick("NK.KKN", *KKN, T0)
    second = Pick("IO.EVN", *EVN, T0 + timedelta(seconds=(d2 - d1) / v))
    return first, second


def test_a_source_in_the_zone_is_feasible_and_the_zone_is_hit() -> None:
    first, second = picks_for_source(*ZONE, v=3.5)
    a = associate(first, second, REGION, zone_lat=ZONE[0], zone_lon=ZONE[1], zone_radius_km=8.0)
    assert a.consistent
    assert a.zone_fraction_feasible > 0.5
    assert 0.0 < a.feasible_fraction < 1.0


def test_a_source_far_from_the_zone_is_rejected() -> None:
    # Something east of Everest: the difference has the wrong sign for the zone.
    first, second = picks_for_source(27.95, 87.3, v=3.5)
    a = associate(first, second, REGION, zone_lat=ZONE[0], zone_lon=ZONE[1], zone_radius_km=8.0)
    assert not a.consistent
    assert a.zone_fraction_feasible == 0.0


def test_the_velocity_range_widens_the_feasible_band() -> None:
    first, second = picks_for_source(*ZONE, v=3.5)
    _, _, narrow = feasible_grid(first, second, REGION, velocity_km_s=(3.4, 3.6))
    _, _, wide = feasible_grid(first, second, REGION, velocity_km_s=(2.5, 6.5))
    assert narrow.sum() < wide.sum()
    assert np.all(wide[narrow]), "the narrow set is inside the wide one"


def test_the_bracket_contains_the_true_second_arrival() -> None:
    first, second = picks_for_source(*ZONE, v=3.0)
    lo, hi = arrival_bracket(first, *EVN, REGION)
    assert lo <= second.onset_utc <= hi


def test_the_bracket_is_finite_and_reported_in_seconds() -> None:
    first = Pick("NK.KKN", *KKN, T0)
    lo, hi = arrival_bracket(first, *EVN, REGION)
    span = (hi - lo).total_seconds()
    assert 0 < span < 300, span


def test_feasible_fraction_reports_how_weak_the_test_is() -> None:
    first, second = picks_for_source(*ZONE, v=3.5)
    a = associate(
        first,
        second,
        REGION,
        zone_lat=ZONE[0],
        zone_lon=ZONE[1],
        zone_radius_km=8.0,
        velocity_km_s=(1.0, 20.0),
        tolerance_s=60.0,
    )
    assert a.feasible_fraction > 0.9, "a test this loose accepts almost everything"
