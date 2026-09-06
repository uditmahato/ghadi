"""Suppressing distant earthquakes (exp004).

**Why this is architecture and not a filter.** exp004 measured the detector's
false-alarm rate against 226 hours of noise and found 12.9 per station-month. Two of
the four surviving false alarms were **teleseisms** — an M6.2 in the Bonin Islands with
an M5.5 in Kamchatka arriving in the same window, and an M6.0 in Indonesia — and they
were the two most extreme, at LF/HF 19.2 and 80.0 against the cascade's 4.14.

That is not bad luck. Attenuation strips high frequencies over thousands of kilometres,
so a distant earthquake arrives low-frequency, long-duration and emergent: **the same
signature GHADI keys on, produced by different physics arriving by a different route.**
No threshold on the spectral features separates them, because on those features they
are not separable. The only reliable discriminant is external: a global earthquake
catalogue, which says a large event happened somewhere far away and predicts when its
energy reaches this station.

It is also the cheapest false alarm to remove. A global M ≥ 5.5 is catalogued within
minutes and its arrival time at a known station is predictable to seconds.

**What this module does not do.** It does not fetch the catalogue — that needs the
network and belongs outside the detection path. It takes an already-retrieved list of
origins and answers whether a detection is explained by one. In operation the caller
keeps a rolling catalogue; in corpus work the caller loads a cached one.

Detection path: numpy only, no obspy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from .geo import haversine_km

# Approximate direct-P travel time for a surface focus, iasp91-like, as
# (epicentral distance in degrees, travel time in seconds). Coarse on purpose: this
# gates a suppression decision with a tolerance window, it does not pick a phase. A
# deeper source arrives earlier, which the tolerance absorbs.
_P_TRAVEL_TABLE: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (5.0, 85.0),
    (10.0, 155.0),
    (20.0, 288.0),
    (30.0, 382.0),
    (40.0, 462.0),
    (50.0, 533.0),
    (60.0, 597.0),
    (70.0, 654.0),
    (80.0, 705.0),
    (90.0, 750.0),
    (100.0, 787.0),
)

KM_PER_DEGREE = 111.195

# Beyond ~100 degrees P is diffracted around the core and both amplitude and timing
# degrade. Suppression still applies — a diffracted arrival can still trip a detector —
# but the window is widened rather than pretending the time is well known.
DIFFRACTED_BEYOND_DEG = 100.0

# Suppression spans a *phase window*, not a tolerance around P. exp006 found the
# rule missing an M6.0 in Indonesia whose trigger fired 647 s after the predicted P —
# and 24 s after the Lg/S arrival. STA/LTA fires on the largest arrival, and for a
# distant earthquake that is S, Lg or the surface train, never P. A P-only rule
# therefore misses the very arrivals most likely to trip the detector.
#
# The window runs from P (minus a lead margin for travel-time model error) to the slow
# surface-wave arrival (plus a trail margin for coda).
SLOW_SURFACE_VELOCITY_KM_S = 3.0
LEAD_MARGIN_S = 90.0
TRAIL_MARGIN_S = 240.0
DIFFRACTED_EXTRA_S = 180.0
# Below roughly this magnitude a teleseism does not carry enough energy to trip a
# regional station, and suppressing on it would start hiding real local events.
DEFAULT_MIN_MAGNITUDE = 5.5


@dataclass(frozen=True)
class Origin:
    """A catalogued earthquake origin, from any global catalogue."""

    time_utc: datetime
    latitude: float
    longitude: float
    magnitude: float
    event_id: str = ""
    place: str = ""


@dataclass(frozen=True)
class Suppression:
    """Why a detection was, or was not, attributed to a distant earthquake."""

    suppressed: bool
    origin: Origin | None
    distance_deg: float | None
    predicted_arrival_utc: datetime | None
    reason: str


def p_travel_time_s(distance_deg: float) -> float:
    """Interpolate the coarse P travel-time table. Clamped at both ends."""
    if distance_deg <= 0:
        return 0.0
    table = _P_TRAVEL_TABLE
    if distance_deg >= table[-1][0]:
        # Extrapolate flatly: beyond 100 deg the curve is nearly flat anyway.
        return table[-1][1]
    for (d0, t0), (d1, t1) in pairwise(table):
        if d0 <= distance_deg <= d1:
            span = d1 - d0
            frac = (distance_deg - d0) / span if span else 0.0
            return t0 + frac * (t1 - t0)
    return table[-1][1]


def surface_wave_travel_time_s(distance_deg: float) -> float:
    """Arrival of the slow end of the surface train.

    Deliberately the *slow* end: this bounds when a distant earthquake's energy has
    finished passing the station, and the suppression window has to cover all of it.
    """
    return distance_deg * KM_PER_DEGREE / SLOW_SURFACE_VELOCITY_KM_S


def epicentral_distance_deg(station_lat: float, station_lon: float, origin: Origin) -> float:
    return haversine_km(station_lat, station_lon, origin.latitude, origin.longitude) / KM_PER_DEGREE


def phase_window(
    origin: Origin, station_lat: float, station_lon: float
) -> tuple[datetime, datetime, float]:
    """When this origin's energy is passing the station: ``(opens, closes, degrees)``.

    From P (minus a lead margin for travel-time model error) to the slow end of the
    surface train (plus a trail margin for coda). Shared by the runtime suppressor and
    by corpus construction, so the two cannot drift apart — a noise corpus excluding
    on one rule while the detector suppresses on another would make the measured
    false-alarm rate describe a system nobody runs.
    """
    distance = epicentral_distance_deg(station_lat, station_lon, origin)
    p_arrival = origin.time_utc + timedelta(seconds=p_travel_time_s(distance))
    surface_arrival = origin.time_utc + timedelta(seconds=surface_wave_travel_time_s(distance))
    extra = DIFFRACTED_EXTRA_S if distance > DIFFRACTED_BEYOND_DEG else 0.0
    opens = p_arrival - timedelta(seconds=LEAD_MARGIN_S + extra)
    closes = surface_arrival + timedelta(seconds=TRAIL_MARGIN_S + extra)
    return opens, closes, distance


def overlaps_window(
    origin: Origin,
    station_lat: float,
    station_lon: float,
    window_start: datetime,
    window_end: datetime,
    min_magnitude: float = DEFAULT_MIN_MAGNITUDE,
) -> bool:
    """Does this origin's energy pass the station at any point during the window?

    Used to keep real earthquakes out of a *noise* corpus. A noise window containing a
    teleseism is a mislabelled positive: it inflates the apparent false-alarm rate
    while teaching a model that events are non-events.
    """
    if origin.magnitude < min_magnitude:
        return False
    opens, closes, _ = phase_window(origin, station_lat, station_lon)
    return opens <= window_end and closes >= window_start


def explain(
    detection_utc: datetime,
    origins: list[Origin] | tuple[Origin, ...],
    station_lat: float,
    station_lon: float,
    min_magnitude: float = DEFAULT_MIN_MAGNITUDE,
) -> Suppression:
    """Is this detection explained by a distant catalogued earthquake?

    Returns the best-matching origin, or a Suppression saying nothing matched. The
    result is deliberately a record rather than a bool: an alert suppressed without a
    stated reason is indistinguishable from an alert that was never raised, and the
    audit log has to be able to tell those apart afterwards.
    """
    if detection_utc.tzinfo is None:
        raise ValueError("detection time must be timezone-aware UTC (HANDOFF §5.3)")

    best: tuple[float, Origin, float, datetime] | None = None
    considered = 0

    for origin in origins:
        if origin.magnitude < min_magnitude:
            continue
        considered += 1
        distance = epicentral_distance_deg(station_lat, station_lon, origin)
        p_arrival = origin.time_utc + timedelta(seconds=p_travel_time_s(distance))
        surface_arrival = origin.time_utc + timedelta(seconds=surface_wave_travel_time_s(distance))
        extra = DIFFRACTED_EXTRA_S if distance > DIFFRACTED_BEYOND_DEG else 0.0
        opens = p_arrival - timedelta(seconds=LEAD_MARGIN_S + extra)
        closes = surface_arrival + timedelta(seconds=TRAIL_MARGIN_S + extra)

        if opens <= detection_utc <= closes:
            # Rank by proximity to P: among overlapping candidates, the one whose
            # direct arrival is closest is the better explanation.
            offset = abs((detection_utc - p_arrival).total_seconds())
            if best is None or offset < best[0]:
                best = (offset, origin, distance, p_arrival)

    if best is None:
        return Suppression(
            suppressed=False,
            origin=None,
            distance_deg=None,
            predicted_arrival_utc=None,
            reason=(
                f"no catalogued M>={min_magnitude} origin has a P-to-surface window "
                f"containing this detection ({considered} considered)"
            ),
        )

    offset, origin, distance, arrival = best
    return Suppression(
        suppressed=True,
        origin=origin,
        distance_deg=distance,
        predicted_arrival_utc=arrival,
        reason=(
            f"M{origin.magnitude:.1f} at {distance:.0f} deg: detection falls in its "
            f"P-to-surface window (P {arrival.strftime('%H:%M:%S')}Z, "
            f"{offset:.0f}s from detection)" + (f" ({origin.place})" if origin.place else "")
        ),
    )
