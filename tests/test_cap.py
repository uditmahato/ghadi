"""CAP emission, and the safety rule that must never be skipped."""

from __future__ import annotations

from datetime import UTC, datetime
from xml.etree import ElementTree as ET

import pytest

from ghadi.cap import CAP_NAMESPACE, CAP_NS, AlertContext, CapSafetyError, build_cap, to_xml
from ghadi.config import AUTHORIZED_BUILD_ENV
from ghadi.fusion import Channel, Tier, fuse


def _context() -> AlertContext:
    return AlertContext(
        event_id="NPL-2026-08-26-BHOTEKOSHI-001",
        detected_utc=datetime(2026, 8, 26, 2, 52, 24, tzinfo=UTC),
        river_reach="Bhote Koshi -> Trishuli",
        model_version="sta_lta@v0.1.0",
        settlements=("Timure", "Syabrubesi", "Bidur"),
        arrival_estimates_min={"Timure": 4, "Syabrubesi": 11, "Bidur": 38},
        exposed_population=1240,
    )


def _decision(alive: bool = True):
    return fuse(
        [
            Channel("seismic_kkn", 0.92, independence_group="seismic"),
            Channel("gauge_timure", 0.88, independence_group="hydro", alive=alive),
        ]
    )


def test_default_build_emits_test_and_restricted() -> None:
    alert = build_cap(_decision(), _context())
    assert alert.findtext("status") == "Test"
    assert alert.findtext("scope") == "Restricted"


def test_actual_status_is_refused_in_a_non_authorised_build() -> None:
    # HANDOFF §15 rule 1. There is a test for this. Do not skip it.
    with pytest.raises(CapSafetyError, match="GHADI_AUTHORIZED_BUILD"):
        build_cap(_decision(), _context(), status="Actual")


def test_public_scope_is_refused_in_a_non_authorised_build() -> None:
    with pytest.raises(CapSafetyError, match="GHADI_AUTHORIZED_BUILD"):
        build_cap(_decision(), _context(), scope="Public")


def test_authorised_build_may_emit_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTHORIZED_BUILD_ENV, "1")
    alert = build_cap(_decision(), _context(), status="Actual", scope="Public")
    assert alert.findtext("status") == "Actual"
    assert alert.findtext("scope") == "Public"


def test_alert_records_the_model_version_that_produced_it() -> None:
    xml = to_xml(build_cap(_decision(), _context()))
    assert "sta_lta@v0.1.0" in xml


def test_alert_states_degradation_in_its_text() -> None:
    xml = to_xml(build_cap(_decision(alive=False), _context()))
    assert "DEGRADED" in xml
    assert "gauge_timure" in xml


def test_warning_tier_maps_to_immediate_and_severe() -> None:
    alert = build_cap(_decision(), _context())
    info = alert.find("info")
    assert info is not None
    assert info.findtext("urgency") == "Immediate"
    assert info.findtext("severity") == "Severe"


def test_cap_is_well_formed_and_in_the_1_2_namespace() -> None:
    xml = to_xml(build_cap(_decision(), _context()))
    assert CAP_NAMESPACE in xml
    root = ET.fromstring(xml)
    assert root.tag == f"{{{CAP_NAMESPACE}}}alert"
    # CAP 1.2 mandatory alert-level elements. Queried through the namespace because
    # that is how a real consumer, parsing the serialised message, will see them.
    for element in ("identifier", "sender", "sent", "status", "msgType", "scope"):
        assert root.find(f"cap:{element}", CAP_NS) is not None, f"missing {element}"


def test_numbers_in_the_description_come_from_the_structured_record() -> None:
    # No generative model produces a number (HANDOFF §15 rule 2): every figure in the
    # text must be traceable to a field on the context or the decision.
    context = _context()
    xml = to_xml(build_cap(_decision(), context))
    assert "1240" in xml  # exposed_population
    assert "38 minutes" in xml  # arrival estimate for Bidur


def test_tier_appears_as_machine_readable_provenance() -> None:
    decision = _decision()
    xml = to_xml(build_cap(decision, _context()))
    assert decision.tier is Tier.WARNING
    assert "ghadi:tier" in xml
    assert "ghadi:cost_ratio_miss_over_fa" in xml
