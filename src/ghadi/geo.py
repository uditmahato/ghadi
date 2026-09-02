"""Geodesy helpers.

Small and dependency-free on purpose: the detection path needs epicentral distance
to reason about travel times, and pulling in a geodesy library for one formula would
put weight on the latency-critical side of the fence.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0

# Crustal P and S velocities, adequate for the regional distances GHADI works at
# (tens to a few hundred km). These are rules of thumb for bounding a search window,
# not a velocity model, and nothing quantitative should be derived from them.
P_VELOCITY_KM_S = 6.0
S_VELOCITY_KM_S = 3.5


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def p_travel_time_s(distance_km: float) -> float:
    """Approximate direct-P travel time. A bound, not a prediction."""
    return distance_km / P_VELOCITY_KM_S


def s_travel_time_s(distance_km: float) -> float:
    """Approximate direct-S travel time.

    The S-P interval matters here for a specific reason: exp002 found that a feature
    intended to measure how slowly a source ramps up was instead measuring S-P, which
    grows with distance. Anything comparing arrival shapes across events must control
    for this.
    """
    return distance_km / S_VELOCITY_KM_S
