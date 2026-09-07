"""Travel-time tables — the detection-to-lead-time bridge, and its n=1 honesty."""

from __future__ import annotations

import pytest

from ghadi.config import DEFAULT, SOURCE_ZONE_LAT, SOURCE_ZONE_LON, TravelConfig
from ghadi.travel import (
    arrival_estimates_min,
    arrival_table,
    lead_times,
    reach_celerity_km_per_min,
)

REACH = "TRISHULI-R07"


def test_calibrated_settlements_return_the_observed_2026_arrivals() -> None:
    est = arrival_estimates_min(REACH)
    assert est == {"Timure": 4.0, "Syabrubesi": 11.0, "Bidur": 38.0}


def test_table_is_ordered_by_arrival_and_carries_provenance() -> None:
    rows = arrival_table(REACH)
    assert [r.settlement for r in rows] == ["Timure", "Syabrubesi", "Bidur"]
    assert all(r.method == "observed_2026" for r in rows)
    # Every figure names itself as single-event calibration, not a model.
    assert all("n=1" in r.note for r in rows)


def test_uncertainty_band_is_initiation_time_only_not_a_confidence_interval() -> None:
    # ±180 s initiation uncertainty => ±3 min around each observed arrival.
    timure = next(r for r in arrival_table(REACH) if r.settlement == "Timure")
    assert timure.low_min == pytest.approx(1.0)
    assert timure.high_min == pytest.approx(7.0)
    assert "not a confidence interval" in timure.note


def test_lead_time_is_arrival_minus_warning_latency() -> None:
    leads = {lt.settlement: lt for lt in lead_times(REACH, warning_latency_s=60.0)}
    # 60 s latency = 1 min subtracted from each surge arrival time.
    assert leads["Bidur"].lead_min == pytest.approx(37.0)
    assert leads["Syabrubesi"].lead_min == pytest.approx(10.0)
    assert leads["Timure"].lead_min == pytest.approx(3.0)


def test_negative_lead_time_is_reported_not_clamped() -> None:
    # If the alert takes longer than the water, the nearest settlement gets no warning.
    # A silently non-negative lead time would lie about exactly the people most at risk.
    leads = {lt.settlement: lt for lt in lead_times(REACH, warning_latency_s=600.0)}
    assert leads["Timure"].lead_min == pytest.approx(-6.0)
    assert not leads["Timure"].actionable
    assert leads["Bidur"].lead_min == pytest.approx(28.0)


def test_actionable_flag_tracks_the_configured_threshold() -> None:
    leads = {lt.settlement: lt for lt in lead_times(REACH, warning_latency_s=60.0)}
    # Default actionable floor is 10 min (Bidur precedent). Timure at 3 min is not;
    # Bidur at 37 min is.
    assert leads["Timure"].actionable is False
    assert leads["Bidur"].actionable is True


def test_out_of_zone_source_falls_back_to_extrapolation_and_says_so() -> None:
    # A source 1 degree north of the calibrated zone (~110 km) invalidates the anchors.
    rows = arrival_table(REACH, source_lat=SOURCE_ZONE_LAT + 1.0, source_lon=SOURCE_ZONE_LON)
    assert all(r.method == "celerity_extrapolation" for r in rows)
    assert all("extrapolated" in r.note for r in rows)
    # The extrapolation band is deliberately wide (±50%), not the ±3 min anchor band.
    timure = next(r for r in rows if r.settlement == "Timure")
    assert timure.low_min == pytest.approx(timure.arrival_min * 0.5)
    assert timure.high_min == pytest.approx(timure.arrival_min * 1.5)


def test_source_within_tolerance_still_uses_observed_anchors() -> None:
    # A few km from the calibrated source is within the source-location uncertainty;
    # the observed arrivals still apply.
    rows = arrival_table(REACH, source_lat=SOURCE_ZONE_LAT + 0.02, source_lon=SOURCE_ZONE_LON)
    assert all(r.method == "observed_2026" for r in rows)


def test_celerity_spread_shows_the_surge_is_not_constant_speed() -> None:
    mean, per = reach_celerity_km_per_min(REACH)
    assert set(per) == {"Timure", "Syabrubesi", "Bidur"}
    assert mean > 0
    # The per-settlement celerities differ materially: that spread is the reason a single
    # constant celerity must not be trusted to extrapolate.
    assert max(per.values()) > 1.5 * min(per.values())


def test_unknown_reach_is_rejected_with_a_helpful_message() -> None:
    with pytest.raises(KeyError, match="unknown river reach"):
        arrival_estimates_min("NOT-A-REACH")


def test_warning_latency_defaults_to_the_configured_budget() -> None:
    cfg = TravelConfig(warning_latency_s=90.0)
    leads = {lt.settlement: lt for lt in lead_times(REACH, config=cfg)}
    assert leads["Bidur"].warning_latency_min == pytest.approx(1.5)
    assert leads["Bidur"].lead_min == pytest.approx(36.5)


def test_default_config_exposes_travel() -> None:
    assert isinstance(DEFAULT.travel, TravelConfig)
