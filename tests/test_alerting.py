"""Assembly of a CAP context from a detection — the minutes-of-warning headline."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ghadi.alerting import build_alert_context
from ghadi.cap import build_cap, to_xml
from ghadi.config import SOURCE_ZONE_LAT, SOURCE_ZONE_LON, TravelConfig
from ghadi.fusion import Channel, fuse

REACH = "TRISHULI-R07"
DETECTED = datetime(2026, 8, 26, 2, 52, 24, tzinfo=UTC)


def _decision(alive: bool = True):
    return fuse(
        [
            Channel("seismic_kkn", 0.92, independence_group="seismic"),
            Channel("gauge_timure", 0.88, independence_group="hydro", alive=alive),
        ]
    )


def _context(warning_latency_s: float = 60.0):
    return build_alert_context(
        event_id="NPL-2026-08-26-BHOTEKOSHI-001",
        detected_utc=DETECTED,
        reach=REACH,
        model_version="sta_lta@v0.1.0",
        warning_latency_s=warning_latency_s,
        exposed_population=1240,
    )


def test_context_carries_lead_times_not_just_arrivals() -> None:
    ctx = _context(warning_latency_s=60.0)
    assert ctx.lead_times_min is not None
    # 60 s warning latency => 1 min subtracted from each surge arrival.
    assert ctx.lead_times_min["Bidur"] == pytest.approx(37.0)
    assert ctx.lead_times_min["Timure"] == pytest.approx(3.0)
    assert ctx.arrival_estimates_min == {"Timure": 4.0, "Syabrubesi": 11.0, "Bidur": 38.0}


def test_context_uses_the_reach_river_system_and_settlements() -> None:
    ctx = _context()
    assert ctx.river_reach == "Lhende Khola -> Bhote Koshi -> Trishuli"
    assert set(ctx.settlements) == {"Timure", "Syabrubesi", "Bidur"}


def test_travel_note_records_method_and_n1_caveat() -> None:
    ctx = _context()
    assert ctx.travel_note is not None
    assert "observed_2026" in ctx.travel_note
    assert "n=1" in ctx.travel_note


def test_description_states_minutes_of_warning_nearest_first() -> None:
    xml = to_xml(build_cap(_decision(), _context(warning_latency_s=60.0)))
    assert "37 minutes of warning" in xml  # Bidur
    assert "surge arrival ~38 min" in xml
    # Nearest settlement (least warning) is stated before the farthest.
    assert xml.index("Timure") < xml.index("Bidur")


def test_negative_lead_time_is_stated_not_hidden() -> None:
    # A slow 10-minute pipeline loses the race to Timure (~4 min surge arrival).
    xml = to_xml(build_cap(_decision(), _context(warning_latency_s=600.0)))
    assert "surge may arrive before this alert" in xml


def test_lead_times_appear_as_machine_readable_parameters() -> None:
    xml = to_xml(build_cap(_decision(), _context()))
    assert "ghadi:lead_min:Bidur" in xml
    assert "ghadi:travel_note" in xml


def test_out_of_zone_source_flags_extrapolation_in_the_alert() -> None:
    ctx = build_alert_context(
        event_id="TEST",
        detected_utc=DETECTED,
        reach=REACH,
        model_version="sta_lta@v0.1.0",
        source_lat=SOURCE_ZONE_LAT + 1.0,
        source_lon=SOURCE_ZONE_LON,
    )
    assert ctx.travel_note is not None and "extrapolation" in ctx.travel_note
    assert "extrapolated" in to_xml(build_cap(_decision(), ctx))


def test_warning_latency_defaults_to_config() -> None:
    ctx = build_alert_context(
        event_id="TEST",
        detected_utc=DETECTED,
        reach=REACH,
        model_version="v",
        config=TravelConfig(warning_latency_s=90.0),
    )
    assert ctx.lead_times_min is not None
    assert ctx.lead_times_min["Bidur"] == pytest.approx(36.5)
