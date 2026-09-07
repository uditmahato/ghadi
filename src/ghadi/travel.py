"""Surge travel-time tables per river reach — the detection-to-lead-time bridge (M4).

This module turns a detection into the project's headline claim: *how many minutes of
warning does each downstream settlement get?* It does one honest thing and refuses to
pretend to do more.

**It is not a hydraulic model.** The only calibration that exists is the single
26 August 2026 event, which delivered the surge to Timure, Syabrubesi and Bidur at
observed times of 4, 11 and 38 minutes after initiation (RESEARCH_REPORT §14.2). The
positive class is n = 1. Every number this module returns is therefore an anchor read
off one event, or an extrapolation from it, and every return says which. The uncertainty
band reflects only the initiation-time uncertainty we can actually quantify (~±3 min);
the dominant uncertainty — one event, no routing model — is unquantified on purpose and
stated in words rather than dressed up as a confidence interval.

Tables are precomputed and looked up; nothing here is on the latency-critical path.
"""

from __future__ import annotations

from dataclasses import dataclass

from ghadi.config import (
    DEFAULT,
    RIVER_REACHES,
    SOURCE_ZONE_ORIGIN_UNCERTAINTY_S,
    RiverReach,
    TravelConfig,
)
from ghadi.geo import haversine_km

# Said once, attached to every figure this module hands out.
_N1_CAVEAT = (
    "single-event calibration (26 Aug 2026, n=1); not a hydraulic model; the band "
    "reflects initiation-time uncertainty only and is not a confidence interval"
)


@dataclass(frozen=True)
class Arrival:
    """Estimated surge arrival at one settlement, with its provenance."""

    settlement: str
    arrival_min: float
    low_min: float
    high_min: float
    reference_distance_km: float
    method: str  # "observed_2026" | "celerity_extrapolation"
    note: str


@dataclass(frozen=True)
class LeadTime:
    """Warning actually delivered at a settlement: arrival minus warning latency."""

    settlement: str
    arrival_min: float
    warning_latency_min: float
    lead_min: float
    actionable: bool
    method: str
    note: str


def _reach(reach: RiverReach | str) -> RiverReach:
    if isinstance(reach, RiverReach):
        return reach
    try:
        return RIVER_REACHES[reach]
    except KeyError:
        known = ", ".join(sorted(RIVER_REACHES)) or "(none)"
        raise KeyError(f"unknown river reach {reach!r}; known reaches: {known}") from None


def reach_celerity_km_per_min(
    reach: RiverReach | str,
) -> tuple[float, dict[str, float]]:
    """Mean straight-line surge celerity implied by the 2026 anchors, and its spread.

    Returned as evidence, not as a model input: the per-settlement values are *not*
    equal (the surge is faster in the steep upper gorge than across the lower valley),
    which is precisely why a single constant celerity must not be trusted to
    extrapolate. Straight-line distance also understates the along-channel path, so
    these celerities are lower bounds on the true water speed.
    """
    r = _reach(reach)
    per_settlement: dict[str, float] = {}
    for s in r.settlements:
        if s.observed_arrival_min_2026 is None or s.observed_arrival_min_2026 <= 0:
            continue
        dist = haversine_km(r.source_lat, r.source_lon, s.lat, s.lon)
        per_settlement[s.name] = dist / s.observed_arrival_min_2026
    if not per_settlement:
        raise ValueError(f"reach {r.reach_id} has no calibrated arrivals to fit celerity")
    mean = sum(per_settlement.values()) / len(per_settlement)
    return mean, per_settlement


def arrival_table(
    reach: RiverReach | str,
    source_lat: float | None = None,
    source_lon: float | None = None,
    config: TravelConfig | None = None,
) -> list[Arrival]:
    """Surge arrival estimate at every settlement on a reach, ordered by arrival.

    With no source given, or a source within the reach's calibrated source zone, the
    observed 2026 arrivals are returned verbatim (``method="observed_2026"``). A source
    materially displaced from the calibrated one invalidates those anchors, so the
    estimate falls back to celerity extrapolation and says so.
    """
    cfg = config or DEFAULT.travel
    r = _reach(reach)
    origin_unc_min = SOURCE_ZONE_ORIGIN_UNCERTAINTY_S / 60.0

    extrapolate = False
    offset_km = 0.0
    if source_lat is not None and source_lon is not None:
        offset_km = haversine_km(r.source_lat, r.source_lon, source_lat, source_lon)
        extrapolate = offset_km > cfg.source_match_tolerance_km

    rows: list[Arrival] = []
    if extrapolate:
        mean_celerity, _ = reach_celerity_km_per_min(r)
        assert source_lat is not None and source_lon is not None
        for s in r.settlements:
            dist = haversine_km(source_lat, source_lon, s.lat, s.lon)
            arrival = dist / mean_celerity
            # Extrapolation widens the band far beyond initiation-time uncertainty:
            # ±50% is a deliberate flag that this figure is unmoored from the one event.
            rows.append(
                Arrival(
                    settlement=s.name,
                    arrival_min=arrival,
                    low_min=max(0.0, arrival * 0.5),
                    high_min=arrival * 1.5,
                    reference_distance_km=dist,
                    method="celerity_extrapolation",
                    note=(
                        f"source is {offset_km:.0f} km from the calibrated 2026 source "
                        f"(> {cfg.source_match_tolerance_km:.0f} km tolerance); "
                        f"extrapolated from mean celerity {mean_celerity:.2f} km/min; "
                        f"{_N1_CAVEAT}"
                    ),
                )
            )
    else:
        for s in r.settlements:
            if s.observed_arrival_min_2026 is None:
                continue
            arrival = s.observed_arrival_min_2026
            dist = haversine_km(r.source_lat, r.source_lon, s.lat, s.lon)
            rows.append(
                Arrival(
                    settlement=s.name,
                    arrival_min=arrival,
                    low_min=max(0.0, arrival - origin_unc_min),
                    high_min=arrival + origin_unc_min,
                    reference_distance_km=dist,
                    method="observed_2026",
                    note=_N1_CAVEAT,
                )
            )
    rows.sort(key=lambda a: a.arrival_min)
    return rows


def arrival_estimates_min(
    river_reach: RiverReach | str,
    source_lat: float | None = None,
    source_lon: float | None = None,
) -> dict[str, float]:
    """Estimated surge arrival time in minutes at each settlement on a reach.

    The plain ``{settlement: minutes}`` view. Use :func:`arrival_table` when the
    provenance and uncertainty of each figure matter — which, given n=1, they always do.
    """
    return {a.settlement: a.arrival_min for a in arrival_table(river_reach, source_lat, source_lon)}


def lead_times(
    reach: RiverReach | str,
    warning_latency_s: float | None = None,
    source_lat: float | None = None,
    source_lon: float | None = None,
    config: TravelConfig | None = None,
) -> list[LeadTime]:
    """Warning delivered at each settlement: surge arrival minus warning latency.

    This is the headline deliverable (M5.2). ``warning_latency_s`` is everything except
    the water's own travel — seismic wave to station, detection, fusion, CAP, hand-off —
    and defaults to the configured budget. A negative lead time means the alert would
    reach the settlement after the water: it is reported as-is, not clamped, because a
    silently non-negative lead time would be a lie about the settlements nearest the
    source (Timure, at ~4 minutes, is the case that most tests this).
    """
    cfg = config or DEFAULT.travel
    latency_s = cfg.warning_latency_s if warning_latency_s is None else warning_latency_s
    latency_min = latency_s / 60.0
    out: list[LeadTime] = []
    for a in arrival_table(reach, source_lat, source_lon, config=cfg):
        lead = a.arrival_min - latency_min
        out.append(
            LeadTime(
                settlement=a.settlement,
                arrival_min=a.arrival_min,
                warning_latency_min=latency_min,
                lead_min=lead,
                actionable=lead >= cfg.actionable_lead_min,
                method=a.method,
                note=a.note,
            )
        )
    return out
