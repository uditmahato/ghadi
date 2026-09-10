"""Cached satellite scene access for ``ghadi.eo``.

ANALYSIS PATH ONLY. This is the satellite counterpart of ``ghadi.fdsn`` and follows the
same contracts:

- Scenes come from the Microsoft Planetary Computer STAC catalogue (free, open
  Copernicus data). Assets are cloud-optimised GeoTIFFs, so only the region of interest
  is read over HTTP range requests; a whole scene is never downloaded.
- Every search and every region read goes through a content-addressed cache under
  ``data/cache/eo``. A second run is offline and byte-identical.
- ``GHADI_OFFLINE=1`` forbids network access; a cache miss is then a failure *record*,
  not an exception. One scene being unavailable never fails a batch.
- The raster and catalogue libraries (``rasterio``, ``pystac_client``,
  ``planetary_computer``) are imported lazily, inside the methods that need them, so
  importing this module costs nothing and the ``eo`` extra is only required when a
  fetch actually happens.

Pairing rule, enforced here because it is the single most important thing in radar
change detection: a before scene and an after scene must share the same relative orbit
and pass direction. Comparing different tracks manufactures change from viewing angle
alone. ``same_track_pairs`` is the only way this module hands out pairs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .config import is_offline

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
SENTINEL1_RTC = "sentinel-1-rtc"  # radar backscatter, terrain corrected, 10 m
SENTINEL2_L2A = "sentinel-2-l2a"  # optical surface reflectance, 10 m bands
# Archive starts. An event before these dates has no scene, and that is a result to
# report, not an error to hide.
SENTINEL1_START = datetime(2014, 10, 1, tzinfo=UTC)
SENTINEL2_START = datetime(2015, 7, 1, tzinfo=UTC)

# Sentinel-2 scene classification (SCL) classes that mean the ground was visible.
# 0 no data, 1 saturated, 2 dark, 3 cloud shadow, 4 vegetation, 5 bare, 6 water,
# 7 unclassified, 8 cloud medium, 9 cloud high, 10 cirrus, 11 snow/ice.
SCL_CLEAR = (4, 5, 6, 7)


def bbox_around(lat: float, lon: float, half_km: float) -> tuple[float, float, float, float]:
    """A square WGS84 bounding box ``(west, south, east, north)`` around a point."""
    dlat = half_km / 111.2
    dlon = half_km / (111.2 * max(np.cos(np.radians(lat)), 1e-6))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def default_cache_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "cache" / "eo"


def sentinel2_clear_mask(scl: np.ndarray) -> np.ndarray:
    """True where the scene classification says the ground was visible."""
    return np.isin(np.asarray(scl), SCL_CLEAR)


def sentinel2_reflectance(dn: np.ndarray) -> np.ndarray:
    """Surface reflectance from L2A digital numbers (offset -1000, scale 1/10000)."""
    return np.clip((np.asarray(dn, dtype=float) - 1000.0) / 10000.0, 0.0, None)


@dataclass(frozen=True)
class SceneMeta:
    """What a search returns: enough to pair scenes and to fetch a region later."""

    item_id: str
    collection: str
    datetime_utc: str  # ISO 8601
    relative_orbit: int | None
    orbit_state: str | None
    cloud_cover: float | None

    @property
    def when(self) -> datetime:
        return datetime.fromisoformat(self.datetime_utc.replace("Z", "+00:00")).astimezone(UTC)


@dataclass
class RoiResult:
    """A region of interest read from one scene, or a failure record."""

    scene: SceneMeta
    asset: str
    array: np.ndarray | None
    transform: tuple[float, float, float, float, float, float] | None  # affine a..f
    epsg: int | None
    pixel_size_m: float | None
    cache_hit: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.array is not None

    @property
    def pixel_area_m2(self) -> float:
        if self.pixel_size_m is None:
            raise ValueError("no pixel size: the read failed")
        return self.pixel_size_m * self.pixel_size_m


def same_track_pairs(
    scenes: list[SceneMeta], event_utc: datetime, max_gap_days: float = 30.0
) -> list[tuple[SceneMeta, SceneMeta]]:
    """The last scene before the event and the first after it, per relative orbit.

    Only scenes on the same relative orbit and pass direction are ever paired. Pairs
    are returned shortest gap first. A track with no scene on one side of the event
    yields no pair, which the caller should report rather than fill in.
    """
    if event_utc.tzinfo is None:
        raise ValueError("event time must be timezone-aware UTC")
    groups: dict[tuple[int | None, str | None], list[SceneMeta]] = {}
    for s in scenes:
        groups.setdefault((s.relative_orbit, s.orbit_state), []).append(s)

    pairs: list[tuple[SceneMeta, SceneMeta]] = []
    for (orbit, _state), members in groups.items():
        if orbit is None:
            continue  # cannot assert same geometry without a track number
        before = [s for s in members if s.when < event_utc]
        after = [s for s in members if s.when >= event_utc]
        if not before or not after:
            continue
        b = max(before, key=lambda s: s.when)
        a = min(after, key=lambda s: s.when)
        if (a.when - b.when).total_seconds() / 86400.0 <= max_gap_days:
            pairs.append((b, a))
    pairs.sort(key=lambda p: (p[1].when - p[0].when).total_seconds())
    return pairs


def _search_key(collection: str, bbox: tuple[float, ...], start: str, end: str) -> str:
    raw = f"{collection}|{','.join(f'{v:.5f}' for v in bbox)}|{start}|{end}"
    return hashlib.sha256(raw.encode()).hexdigest()


def roi_cache_key(item_id: str, asset: str, bbox: tuple[float, ...]) -> str:
    raw = f"{item_id}|{asset}|{','.join(f'{v:.5f}' for v in bbox)}"
    return hashlib.sha256(raw.encode()).hexdigest()


class CachedSceneClient:
    """STAC search and windowed raster reads with a write-once cache."""

    def __init__(self, cache_dir: Path | None = None, stac_url: str = STAC_URL) -> None:
        self.cache_dir = cache_dir or default_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.stac_url = stac_url
        self._catalog: Any | None = None

    # -- catalogue ---------------------------------------------------------------
    def _open_catalog(self) -> Any:
        if self._catalog is None:
            import planetary_computer
            import pystac_client

            self._catalog = pystac_client.Client.open(
                self.stac_url, modifier=planetary_computer.sign_inplace
            )
        return self._catalog

    def search(
        self,
        collection: str,
        bbox: tuple[float, float, float, float],
        start: datetime,
        end: datetime,
    ) -> tuple[list[SceneMeta], str | None]:
        """Scenes touching ``bbox`` in ``[start, end]``. Cached; offline-safe."""
        s = start.astimezone(UTC).isoformat(timespec="seconds")
        e = end.astimezone(UTC).isoformat(timespec="seconds")
        path = self.cache_dir / f"search_{_search_key(collection, bbox, s, e)}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return [SceneMeta(**d) for d in data], None
        if is_offline():
            return [], f"offline mode: search for {collection} not in cache"
        try:
            found = self._open_catalog().search(
                collections=[collection], bbox=list(bbox), datetime=f"{s}/{e}", max_items=200
            )
            metas: list[SceneMeta] = []
            for item in found.items():
                p = item.properties
                metas.append(
                    SceneMeta(
                        item_id=item.id,
                        collection=collection,
                        datetime_utc=str(p.get("datetime")),
                        relative_orbit=p.get("sat:relative_orbit"),
                        orbit_state=p.get("sat:orbit_state"),
                        cloud_cover=p.get("eo:cloud_cover"),
                    )
                )
            metas.sort(key=lambda m: m.when)
            tmp = path.with_suffix(".part")
            tmp.write_text(json.dumps([asdict(m) for m in metas]), encoding="utf-8")
            tmp.replace(path)
            return metas, None
        except Exception as exc:
            return [], f"{type(exc).__name__}: {exc}"

    # -- rasters -----------------------------------------------------------------
    def read_roi(
        self, scene: SceneMeta, asset: str, bbox: tuple[float, float, float, float]
    ) -> RoiResult:
        """Read one asset over ``bbox`` from one scene. Cached; offline-safe."""
        path = self.cache_dir / f"roi_{roi_cache_key(scene.item_id, asset, bbox)}.npz"
        if path.exists():
            return self._read_cached(scene, asset, path)
        if is_offline():
            return RoiResult(
                scene,
                asset,
                None,
                None,
                None,
                None,
                cache_hit=False,
                error=f"offline mode: {scene.item_id}/{asset} not in cache",
            )
        return self._fetch_and_cache(scene, asset, bbox, path)

    def _read_cached(self, scene: SceneMeta, asset: str, path: Path) -> RoiResult:
        try:
            with np.load(path) as z:
                arr = z["array"]
                tr = tuple(float(v) for v in z["transform"])
                epsg = int(z["epsg"])
                px = float(z["pixel_size_m"])
            assert len(tr) == 6
            return RoiResult(scene, asset, arr, tr, epsg, px, cache_hit=True)
        except Exception as exc:
            return RoiResult(
                scene,
                asset,
                None,
                None,
                None,
                None,
                cache_hit=True,
                error=f"cache read failed for {path.name}: {exc}",
            )

    def _fetch_and_cache(
        self, scene: SceneMeta, asset: str, bbox: tuple[float, ...], path: Path
    ) -> RoiResult:
        try:
            import rasterio
            from rasterio.warp import transform_bounds
            from rasterio.windows import from_bounds

            found = self._open_catalog().search(
                collections=[scene.collection], ids=[scene.item_id], max_items=1
            )
            item = next(found.items())
            href = item.assets[asset].href
            with rasterio.open(href) as src:
                wb = transform_bounds("EPSG:4326", src.crs, *bbox)
                win = from_bounds(*wb, transform=src.transform)
                arr = src.read(1, window=win).astype(np.float32)
                if src.nodata is not None:
                    arr = np.where(arr == src.nodata, np.nan, arr)
                t = src.window_transform(win)
                tr = (float(t.a), float(t.b), float(t.c), float(t.d), float(t.e), float(t.f))
                epsg = int(src.crs.to_epsg() or 0)
                px = float(abs(t.a))
            tmp = path.with_suffix(".part.npz")
            np.savez_compressed(
                tmp,
                array=arr,
                transform=np.array(tr),
                epsg=np.array(epsg),
                pixel_size_m=np.array(px),
            )
            tmp.replace(path)
            return RoiResult(scene, asset, arr, tr, epsg, px, cache_hit=False)
        except Exception as exc:
            return RoiResult(
                scene,
                asset,
                None,
                None,
                None,
                None,
                cache_hit=False,
                error=f"{type(exc).__name__}: {exc}",
            )


def rowcol_to_lonlat(roi: RoiResult, row: float, col: float) -> tuple[float, float]:
    """Map a pixel position in a read region back to WGS84 ``(lon, lat)``."""
    if roi.transform is None or roi.epsg is None:
        raise ValueError("cannot geolocate a failed read")
    from rasterio.warp import transform as warp_transform

    a, b, c, d, e, f = roi.transform
    x = c + a * (col + 0.5) + b * (row + 0.5)
    y = f + d * (col + 0.5) + e * (row + 0.5)
    xs, ys = warp_transform(f"EPSG:{roi.epsg}", "EPSG:4326", [x], [y])
    return float(xs[0]), float(ys[0])
