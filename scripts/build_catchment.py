"""Derive the catchment above a river point from an open elevation model.

    python scripts/build_catchment.py            # the Trishuli above Bidur

The location test in ``ghadi.associate`` asked whether a source could lie inside a box
drawn by hand. This replaces the box with the real thing: every cell of ground whose
water drains past the outlet.

**Method.** The Copernicus 90 m elevation model for the region, read from the Microsoft
Planetary Computer. A priority flood from the edges of the grid inward assigns every
cell the neighbour its water leaves by, which also carries water across pits and flat
ground without a separate filling step (Barnes, Lehman and Mulla 2014). Counting cells
upstream of each cell gives the river network, the outlet is moved to the largest
river within 5 km of the stated point, and the catchment is every cell that drains
to it. The outline is the boundary of that set, simplified, as GeoJSON.

The elevation model needs the network and the ``eo`` extra. The result is committed in
``data/geo``, so nothing downstream needs either.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "cop-dem-glo-90"
BBOX = (84.6, 27.7, 86.1, 29.4)  # lon_min, lat_min, lon_max, lat_max
OUTLET = ("Bidur", 27.870, 85.162)
SNAP_KM = 5.0
OUT = REPO / "data" / "geo" / "trishuli_above_bidur.geojson"
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


DEM_CACHE = REPO / "data" / "cache" / "eo" / "dem_glo90_trishuli.npz"


def read_dem() -> tuple[np.ndarray, Any]:
    from rasterio.transform import Affine

    if DEM_CACHE.exists():
        saved = np.load(DEM_CACHE)
        return saved["dem"], Affine(*saved["transform"])
    dem, transform = fetch_dem()
    DEM_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(DEM_CACHE, dem=dem, transform=np.array(tuple(transform)[:6]))
    return dem, transform


def fetch_dem() -> tuple[np.ndarray, Any]:
    import planetary_computer
    import pystac_client
    import rasterio
    from rasterio.merge import merge

    catalog = pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = list(catalog.search(collections=[COLLECTION], bbox=list(BBOX)).items())
    if not items:
        raise SystemExit("no elevation tiles found for the region")
    sources = [rasterio.open(item.assets["data"].href) for item in items]
    try:
        mosaic, transform = merge(sources, bounds=BBOX)
    finally:
        for s in sources:
            s.close()
    return mosaic[0].astype(np.float32), transform


def drainage(dem: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Where each cell's water goes, and the order cells were reached from the edge.

    Returns ``parent`` (the flat index of the cell each cell drains to, -1 at the grid
    edge) and ``order`` (flat indices from the edge inward). A cell is always reached
    after the cell it drains to, so walking ``order`` backwards visits every cell
    before its parent.
    """
    rows, cols = dem.shape
    # Plain lists and a bytearray: this loop touches every cell eight times, and numpy
    # scalar access would make it several times slower.
    flat: list[float] = dem.ravel().tolist()
    parent = [-1] * (rows * cols)
    done = bytearray(rows * cols)
    order: list[int] = []
    heap: list[tuple[float, int]] = []
    edge = [r * cols + c for r in range(rows) for c in (0, cols - 1)]
    edge += [r * cols + c for c in range(cols) for r in (0, rows - 1)]
    for i in edge:
        if not done[i]:
            done[i] = 1
            heap.append((flat[i], i))
    heapq.heapify(heap)
    push, pop = heapq.heappush, heapq.heappop
    while heap:
        level, i = pop(heap)
        order.append(i)
        r, c = divmod(i, cols)
        for dr, dc in NEIGHBOURS:
            rr, cc = r + dr, c + dc
            if 0 <= rr < rows and 0 <= cc < cols:
                j = rr * cols + cc
                if not done[j]:
                    done[j] = 1
                    parent[j] = i
                    # A pit is raised to the level of the cell it is reached from, so
                    # its water leaves by that cell.
                    z = flat[j]
                    push(heap, (z if z > level else level, j))
    return np.asarray(parent, dtype=np.int64), np.asarray(order, dtype=np.int64)


def accumulation(parent: np.ndarray, order: np.ndarray) -> np.ndarray:
    acc = [1] * parent.size
    par = parent.tolist()
    for i in order[::-1].tolist():
        p = par[i]
        if p >= 0:
            acc[p] += acc[i]
    return np.asarray(acc, dtype=np.int64)


def catchment(parent: np.ndarray, order: np.ndarray, outlet: int) -> np.ndarray:
    inside = bytearray(parent.size)
    inside[outlet] = 1
    par = parent.tolist()
    for i in order.tolist():  # a parent is always visited before its children
        p = par[i]
        if p >= 0 and inside[p]:
            inside[i] = 1
    return np.frombuffer(bytes(inside), dtype=np.uint8).astype(bool)


def simplify(ring: list[list[float]], tolerance: float) -> list[list[float]]:
    """Douglas and Peucker line simplification, iterative."""
    if len(ring) < 4:
        return ring
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    if ring[0] == ring[-1]:
        # A closed ring has no baseline between its ends. Split it at the point
        # furthest from the start so each half has one.
        x0, y0 = ring[0]
        far = max(range(len(ring)), key=lambda k: (ring[k][0] - x0) ** 2 + (ring[k][1] - y0) ** 2)
        keep[far] = True
        stack = [(0, far), (far, len(ring) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = ring[a]
        bx, by = ring[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-12
        far, far_d = -1, tolerance
        for k in range(a + 1, b):
            px, py = ring[k]
            d = abs(dy * (px - ax) - dx * (py - ay)) / norm
            if d > far_d:
                far, far_d = k, d
        if far >= 0:
            keep[far] = True
            stack.extend(((a, far), (far, b)))
    return [p for p, k in zip(ring, keep, strict=True) if k]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)

    from rasterio.features import shapes
    from rasterio.transform import rowcol

    dem, transform = read_dem()
    rows, cols = dem.shape
    print(f"elevation grid {rows} x {cols}")
    parent, order = drainage(dem)
    acc = accumulation(parent, order)

    name, lat, lon = OUTLET
    r0, c0 = rowcol(transform, lon, lat)
    cell_km_y = abs(transform.e) * 111.195
    cell_km_x = abs(transform.a) * 111.195 * math.cos(math.radians(lat))
    reach_r = max(int(SNAP_KM / cell_km_y), 1)
    reach_c = max(int(SNAP_KM / cell_km_x), 1)
    best, best_acc = (r0, c0), -1
    for r in range(max(r0 - reach_r, 0), min(r0 + reach_r + 1, rows)):
        for c in range(max(c0 - reach_c, 0), min(c0 + reach_c + 1, cols)):
            a = int(acc[r * cols + c])
            if a > best_acc:
                best, best_acc = (r, c), a
    outlet = best[0] * cols + best[1]
    inside = catchment(parent, order, outlet).reshape(rows, cols)

    lat_of_row = transform.f + (np.arange(rows) + 0.5) * transform.e
    cell_area = (abs(transform.e) * 111.195) * (
        abs(transform.a) * 111.195 * np.cos(np.radians(lat_of_row))
    )
    area_km2 = float((inside * cell_area[:, None]).sum())
    touches_edge = bool(
        inside[0].any() or inside[-1].any() or inside[:, 0].any() or inside[:, -1].any()
    )

    polygons = [
        geom
        for geom, value in shapes(inside.astype(np.uint8), mask=inside, transform=transform)
        if value == 1
    ]
    ring = max((g["coordinates"][0] for g in polygons), key=len)
    ring = simplify([[float(x), float(y)] for x, y in ring], tolerance=0.004)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    outlet_lon, outlet_lat = transform * (best[1] + 0.5, best[0] + 0.5)
    feature = {
        "type": "Feature",
        "properties": {
            "name": f"Trishuli catchment above {name}",
            "outlet_stated": {"lat": lat, "lon": lon},
            "outlet_snapped": {"lat": round(outlet_lat, 5), "lon": round(outlet_lon, 5)},
            "area_km2": round(area_km2, 0),
            "cells": int(inside.sum()),
            "touches_grid_edge": touches_edge,
            "elevation_model": "Copernicus DEM GLO-90, via Microsoft Planetary Computer",
            "method": "priority flood drainage (Barnes et al. 2014), D8 neighbours",
            "simplify_tolerance_deg": 0.004,
            "built_utc": datetime.now(tz=UTC).isoformat(),
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[round(x, 5), round(y, 5)] for x, y in ring]],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(feature, indent=1), encoding="utf-8")
    print(f"outlet snapped to {outlet_lat:.4f} N, {outlet_lon:.4f} E, {best_acc} cells upstream")
    print(
        f"catchment area {area_km2:.0f} km2, {len(ring)} outline points, "
        f"touches edge: {touches_edge}"
    )
    print(f"wrote {args.out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
