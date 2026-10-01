"""The catchment above a river point, as an outline the location test can use.

``ghadi.associate`` asks whether two stations' arrival times fit a source in some
region. The region that matters is the ground that drains to the settlements being
warned. ``scripts/build_catchment.py`` derives that ground from an open elevation
model and stores its outline in ``data/geo``; this module reads the outline and
answers "is this point inside it".

The outline is simplified to a few hundred points, so a point within a few hundred
metres of the divide can fall on the wrong side. The location test's own uncertainty
is tens of kilometres, so that does not matter here. It would matter for hydrology.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["Basin", "default_basin_path", "load_basin"]


def default_basin_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "geo" / "trishuli_above_bidur.geojson"


@dataclass(frozen=True)
class Basin:
    name: str
    lons: np.ndarray  # outline, closed
    lats: np.ndarray
    area_km2: float
    properties: dict[str, Any]

    def contains(self, lats: np.ndarray | float, lons: np.ndarray | float) -> np.ndarray:
        """True where a point is inside the outline. Even odd rule, vectorised."""
        la = np.atleast_1d(np.asarray(lats, dtype=float))
        lo = np.atleast_1d(np.asarray(lons, dtype=float))
        inside = np.zeros(la.shape, dtype=bool)
        x1, y1 = self.lons[:-1], self.lats[:-1]
        x2, y2 = self.lons[1:], self.lats[1:]
        for ax, ay, bx, by in zip(x1, y1, x2, y2, strict=True):
            if ay == by:
                continue
            crosses = (ay > la) != (by > la)
            x_at = ax + (la - ay) * (bx - ax) / (by - ay)
            inside ^= crosses & (lo < x_at)
        return inside

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """lat_min, lat_max, lon_min, lon_max."""
        return (
            float(self.lats.min()),
            float(self.lats.max()),
            float(self.lons.min()),
            float(self.lons.max()),
        )


def load_basin(path: str | Path | None = None) -> Basin:
    p = Path(path) if path is not None else default_basin_path()
    feature = json.loads(p.read_text(encoding="utf-8"))
    ring = feature["geometry"]["coordinates"][0]
    lons = np.array([pt[0] for pt in ring], dtype=float)
    lats = np.array([pt[1] for pt in ring], dtype=float)
    if lons[0] != lons[-1] or lats[0] != lats[-1]:
        lons, lats = np.append(lons, lons[0]), np.append(lats, lats[0])
    props = feature.get("properties", {})
    return Basin(
        name=str(props.get("name", p.stem)),
        lons=lons,
        lats=lats,
        area_km2=float(props.get("area_km2", float("nan"))),
        properties=props,
    )
