"""Assemble a CAP alert context from a detection and a river reach (M5.2).

This is the layer between detection/travel and CAP emission. It computes the lead time
delivered at each settlement — the project's headline figure — and packs it into the
structured ``AlertContext`` that ``ghadi.cap`` templates. Keeping it here preserves
``ghadi.cap``'s contract that it is a pure templater fed by structured records and never
computes anything itself.

It is *not* the real-time loop (``ghadi.service``, still blocked on the SeedLink latency
run, issue 0.1). Nothing here touches the network; it is the offline assembly that the
retrospective headline analysis and, later, the live loop both call.
"""

from __future__ import annotations

from datetime import datetime

from ghadi.cap import AlertContext
from ghadi.config import RiverReach, TravelConfig
from ghadi.travel import get_reach, lead_times


def build_alert_context(
    event_id: str,
    detected_utc: datetime,
    reach: RiverReach | str,
    model_version: str,
    warning_latency_s: float | None = None,
    source_lat: float | None = None,
    source_lon: float | None = None,
    exposed_population: int | None = None,
    config: TravelConfig | None = None,
) -> AlertContext:
    """Build the CAP context for a detection on ``reach``, with per-settlement lead time.

    ``warning_latency_s`` is everything between initiation and an issued alert (defaults
    to the configured budget). ``source_lat``/``source_lon``, if given, decide whether
    the observed 2026 anchors still apply or the figures fall back to flagged
    extrapolation — the resulting method and caveat travel into the alert verbatim.
    """
    leads = lead_times(
        reach,
        warning_latency_s=warning_latency_s,
        source_lat=source_lat,
        source_lon=source_lon,
        config=config,
    )
    if not leads:
        raise ValueError(f"reach {reach!r} yielded no settlements to warn")

    arrivals = {lt.settlement: lt.arrival_min for lt in leads}
    lead_map = {lt.settlement: lt.lead_min for lt in leads}
    # Method and caveat are uniform across a reach's settlements; carry one copy.
    travel_note = f"{leads[0].method}; {leads[0].note}"
    reach_obj = get_reach(reach)

    return AlertContext(
        event_id=event_id,
        detected_utc=detected_utc,
        river_reach=reach_obj.river_system,
        model_version=model_version,
        settlements=tuple(lt.settlement for lt in leads),
        arrival_estimates_min=arrivals,
        lead_times_min=lead_map,
        travel_note=travel_note,
        exposed_population=exposed_population,
    )
