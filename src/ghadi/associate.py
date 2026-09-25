"""Associate arrivals across stations and ask where the source could be (issue #31).

One station gives a time. Two stations give a time difference, and a time difference
constrains where the source can be: every candidate point predicts its own difference
from the distances to the two stations and the wave speed. This module turns two onset
picks into a map of feasible source points and answers two questions:

* **Is the catalogued source zone feasible?** If the picks cannot be explained by any
  point in the zone at any plausible speed, they are not the same event, or the event
  is not there.
* **How selective was that?** The share of the search region that is feasible says how
  much the test could have rejected. A test that accepts most of the region has not
  said much, and the number is reported so nobody mistakes a weak test for a strong one.

The wave speed is a range, not a value, because a landslide signal's first trigger may
sit on P energy, S energy, or surface waves depending on distance and size, and the
onset picker does not say which. The range makes the test honest and weaker; narrowing
it needs evidence this project does not yet have.

Two seismic stations share a failure mode and are **not** two independence groups in
fusion. This module makes the single seismic channel harder to fool. It does not
manufacture a second source of evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from .geo import haversine_km

__all__ = [
    "Association",
    "Pick",
    "SearchRegion",
    "arrival_bracket",
    "associate",
    "feasible_grid",
]

# Direct P is about 6 km/s in the crust; surface waves on a thick sedimentary path can
# be under 3 km/s. A pick on either end has to be allowed.
DEFAULT_VELOCITY_KM_S: tuple[float, float] = (2.5, 6.5)
DEFAULT_TOLERANCE_S = 5.0  # onset picking error on each station, roughly


@dataclass(frozen=True)
class Pick:
    station: str
    lat: float
    lon: float
    onset_utc: datetime


@dataclass(frozen=True)
class SearchRegion:
    """The box of candidate source points. Deliberately generous."""

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    step_km: float = 2.0

    def grid(self) -> tuple[np.ndarray, np.ndarray]:
        """Latitude and longitude arrays of the grid points, flattened."""
        lat_step = self.step_km / 111.0
        mid = 0.5 * (self.lat_min + self.lat_max)
        lon_step = self.step_km / (111.0 * max(np.cos(np.radians(mid)), 1e-6))
        lats = np.arange(self.lat_min, self.lat_max + 1e-9, lat_step)
        lons = np.arange(self.lon_min, self.lon_max + 1e-9, lon_step)
        grid_lat, grid_lon = np.meshgrid(lats, lons, indexing="ij")
        return grid_lat.ravel(), grid_lon.ravel()

    @property
    def cell_area_km2(self) -> float:
        return self.step_km * self.step_km


def _distances(lats: np.ndarray, lons: np.ndarray, lat: float, lon: float) -> np.ndarray:
    return np.array(
        [haversine_km(float(a), float(b), lat, lon) for a, b in zip(lats, lons, strict=True)]
    )


def feasible_grid(
    first: Pick,
    second: Pick,
    region: SearchRegion,
    *,
    velocity_km_s: tuple[float, float] = DEFAULT_VELOCITY_KM_S,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Which grid points can explain the observed time difference at some speed.

    Returns the grid latitudes, longitudes, and a boolean mask.
    """
    v_lo, v_hi = velocity_km_s
    if v_lo <= 0 or v_hi < v_lo:
        raise ValueError("velocity range must be positive and ordered")
    lats, lons = region.grid()
    d1 = _distances(lats, lons, first.lat, first.lon)
    d2 = _distances(lats, lons, second.lat, second.lon)
    observed = (second.onset_utc - first.onset_utc).total_seconds()
    delta = d2 - d1
    # Predicted difference is delta / v, monotonic in v, so the extremes are at the ends.
    lo = np.minimum(delta / v_lo, delta / v_hi)
    hi = np.maximum(delta / v_lo, delta / v_hi)
    mask = (observed >= lo - tolerance_s) & (observed <= hi + tolerance_s)
    return lats, lons, mask


@dataclass(frozen=True)
class Association:
    stations: tuple[str, str]
    time_difference_s: float  # second minus first
    feasible_fraction: float  # share of the search region that fits the picks
    feasible_area_km2: float
    zone_feasible: bool  # does any point of the catalogued zone fit
    zone_fraction_feasible: float  # share of zone grid points that fit
    velocity_km_s: tuple[float, float]
    tolerance_s: float
    n_grid: int

    @property
    def consistent(self) -> bool:
        """Both stations can be looking at one source in the zone."""
        return self.zone_feasible

    def as_dict(self) -> dict[str, object]:
        return {
            "stations": list(self.stations),
            "time_difference_s": round(self.time_difference_s, 2),
            "feasible_fraction": round(self.feasible_fraction, 4),
            "feasible_area_km2": round(self.feasible_area_km2, 1),
            "zone_feasible": self.zone_feasible,
            "zone_fraction_feasible": round(self.zone_fraction_feasible, 4),
            "velocity_km_s": list(self.velocity_km_s),
            "tolerance_s": self.tolerance_s,
            "n_grid": self.n_grid,
        }


def associate(
    first: Pick,
    second: Pick,
    region: SearchRegion,
    *,
    zone_lat: float,
    zone_lon: float,
    zone_radius_km: float,
    velocity_km_s: tuple[float, float] = DEFAULT_VELOCITY_KM_S,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> Association:
    """Test two picks against a catalogued source zone inside a search region."""
    lats, lons, mask = feasible_grid(
        first, second, region, velocity_km_s=velocity_km_s, tolerance_s=tolerance_s
    )
    in_zone = _distances(lats, lons, zone_lat, zone_lon) <= zone_radius_km
    zone_hits = int(np.count_nonzero(mask & in_zone))
    zone_points = int(np.count_nonzero(in_zone))
    return Association(
        stations=(first.station, second.station),
        time_difference_s=(second.onset_utc - first.onset_utc).total_seconds(),
        feasible_fraction=float(np.count_nonzero(mask)) / max(mask.size, 1),
        feasible_area_km2=float(np.count_nonzero(mask)) * region.cell_area_km2,
        zone_feasible=zone_hits > 0,
        zone_fraction_feasible=zone_hits / zone_points if zone_points else 0.0,
        velocity_km_s=velocity_km_s,
        tolerance_s=tolerance_s,
        n_grid=int(mask.size),
    )


def arrival_bracket(
    pick: Pick,
    other_lat: float,
    other_lon: float,
    region: SearchRegion,
    *,
    velocity_km_s: tuple[float, float] = DEFAULT_VELOCITY_KM_S,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
) -> tuple[datetime, datetime]:
    """When the other station must have seen the arrival, for any source in the region.

    Used the other way round from ``associate``: given one station's onset, this is the
    time span in which the second station has to trigger for the two to be one event
    anywhere in the region. A trigger outside it cannot be the same source.
    """
    v_lo, v_hi = velocity_km_s
    lats, lons = region.grid()
    d_here = _distances(lats, lons, pick.lat, pick.lon)
    d_other = _distances(lats, lons, other_lat, other_lon)
    delta = d_other - d_here
    lo = float(np.min(np.minimum(delta / v_lo, delta / v_hi))) - tolerance_s
    hi = float(np.max(np.maximum(delta / v_lo, delta / v_hi))) + tolerance_s
    return pick.onset_utc + timedelta(seconds=lo), pick.onset_utc + timedelta(seconds=hi)
