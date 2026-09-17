"""Rank a radar event window against like-for-like no-event windows.

ANALYSIS PATH ONLY. This is the comparison exp014 ran for 2026, lifted into the library
so that every later use (earlier years, other events) follows the same rules:

- **The statistic** is ``ghadi.eo.cross_track_excess``: per track, pixels that changed in
  the window and not in that track's own control; the largest connected patch where at
  least ``min_tracks`` tracks agree.
- **Like with like.** "Two of two agree" is a harder bar than "two of three", so a null
  window with fewer tracks than the event would come out smaller and flatter the event.
  Each null is compared with the event recomputed on exactly the null's track set, and
  results are grouped by track set.
- **Rank, with its floor.** The empirical rank is ``(1 + nulls at or above the event) /
  (1 + nulls)``. With few nulls that number cannot be small, and it is reported as it is,
  never dressed up as significance.
- **Polarisations are processed independently**, and where the same window and track set
  exist in two polarisations their agreement maps are compared (Jaccard overlap).

The caller supplies the windows (``ghadi.eo_fetch.cycle_windows`` builds them) and a
client with ``read_roi``; this module never searches or chooses windows itself.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations
from typing import Any, Protocol

import numpy as np

from .config import DEFAULT, EoConfig
from .eo import cross_track_excess, sar_change_masks
from .eo_fetch import Bbox, CycleWindow, RoiResult, SceneMeta, align_arrays, cycle_windows

Subset = tuple[int, ...]
Transform = tuple[float, float, float, float, float, float]
# (grid transform, epsg, row, col) -> extra fields for a patch centroid
Locator = Callable[[Transform, int, float, float], dict[str, Any]]


class RoiReader(Protocol):
    def read_roi(self, scene: SceneMeta, asset: str, bbox: Bbox) -> RoiResult: ...


@dataclass(frozen=True)
class WindowSet:
    """One test window across tracks: an event window or one no-event (null) window."""

    label: str  # e.g. "2026 lag 0", "2024 lag 2"
    role: str  # "event" | "null"
    windows: dict[int, CycleWindow]  # relative orbit -> window


def _scenes(sets: list[WindowSet]) -> dict[str, SceneMeta]:
    return {
        s.item_id: s
        for ws in sets
        for w in ws.windows.values()
        for s in (w.control_before, w.before, w.after)
    }


def _statistic(
    arrays: dict[str, np.ndarray],
    windows: list[CycleWindow],
    min_tracks: int,
    cfg: EoConfig,
    locate: Callable[[float, float], dict[str, Any]] | None,
) -> tuple[dict[str, Any], np.ndarray]:
    ev, ct, va = [], [], []
    for w in windows:
        b = arrays[w.before.item_id]
        a = arrays[w.after.item_id]
        c = arrays[w.control_before.item_id]
        e_change, _, _, e_valid = sar_change_masks(b, a, config=cfg)
        c_change, _, _, c_valid = sar_change_masks(c, b, config=cfg)
        ev.append(e_change)
        ct.append(c_change)
        va.append(e_valid & c_valid)
    res = cross_track_excess(ev, ct, va, cfg.pixel_size_m**2, min_tracks)
    agree = np.zeros(ev[0].shape, dtype=np.int16)
    for e, c, v in zip(ev, ct, va, strict=True):
        agree += (e & ~c & v).astype(np.int16)
    out: dict[str, Any] = {
        "largest_patch_km2": round(res.largest_patch_km2, 4),
        "area_km2_by_agreement": {
            str(k): round(v, 3) for k, v in res.area_km2_by_agreement.items()
        },
        "per_track_excess_km2": [round(v, 3) for v in res.per_track_excess_km2],
    }
    if res.largest_patch_centroid_rc is not None and locate is not None:
        out.update(locate(*res.largest_patch_centroid_rc))
    return out, agree >= min_tracks


def rank_summary(event_value: float, null_values: list[float]) -> dict[str, Any]:
    """Empirical rank of an event among nulls, with the floor stated."""
    if not null_values:
        raise ValueError("no null values to rank against")
    ge = sum(v >= event_value for v in null_values)
    n = len(null_values)
    top = max(null_values)
    return {
        "event_largest_km2": event_value,
        "null_largest_km2": null_values,
        "n_null": n,
        "null_max_km2": top,
        "null_median_km2": round(float(np.median(null_values)), 4),
        "event_over_null_max": round(event_value / top, 2) if top > 0 else None,
        "null_windows_at_or_above_event": ge,
        "empirical_p": round((1 + ge) / (1 + n), 3),
        "p_floor": round(1 / (1 + n), 3),
    }


def compare_event_to_nulls(
    client: RoiReader,
    bbox: Bbox,
    event: WindowSet,
    nulls: list[WindowSet],
    pols: tuple[str, ...] = ("vv", "vh"),
    min_tracks: int = 2,
    config: EoConfig | None = None,
    locate: Locator | None = None,
) -> dict[str, Any]:
    """Run the cross-track test on the event and every null, per polarisation.

    ``locate(transform, epsg, row, col)`` may map a patch centroid on the common grid to
    extra fields, for example latitude, longitude, and distance from a source.
    """
    cfg = config or DEFAULT.eo
    if event.role != "event" or any(n.role != "null" for n in nulls):
        raise ValueError("expected one event WindowSet and only null WindowSets")
    needed = _scenes([event, *nulls])
    out: dict[str, Any] = {"polarisations": {}}
    masks: dict[str, dict[tuple[str, Subset], np.ndarray]] = {}

    for pol in pols:
        rois: dict[str, RoiResult] = {}
        failures = []
        for item_id, scene in sorted(needed.items(), key=lambda kv: kv[1].when):
            r = client.read_roi(scene, pol, bbox)
            if r.ok:
                rois[item_id] = r
            else:
                failures.append({"item_id": item_id, "error": r.error})
        pol_rec: dict[str, Any] = {"failures": failures, "groups": []}
        out["polarisations"][pol] = pol_rec
        masks[pol] = {}
        if not rois:
            pol_rec["status"] = "no_regions"
            continue
        ids = list(rois)
        aligned, common = align_arrays([rois[i] for i in ids])
        arrays = dict(zip(ids, aligned, strict=True))
        epsg = rois[ids[0]].epsg or 0
        pol_rec["grid_shape"] = list(aligned[0].shape)
        loc = None if locate is None else (lambda r, c, _t=common, _e=epsg: locate(_t, _e, r, c))

        def usable(ws: WindowSet, arrays: dict[str, np.ndarray] = arrays) -> dict[int, CycleWindow]:
            return {
                o: w
                for o, w in ws.windows.items()
                if all(s.item_id in arrays for s in (w.control_before, w.before, w.after))
            }

        ev_windows = usable(event)
        ev_tracks = tuple(sorted(ev_windows))
        pol_rec["event_tracks"] = list(ev_tracks)
        cache: dict[tuple[str, Subset], dict[str, Any]] = {}

        def stat(
            ws: WindowSet,
            wins: dict[int, CycleWindow],
            subset: Subset,
            arrays: dict[str, np.ndarray] = arrays,
            cache: dict[tuple[str, Subset], dict[str, Any]] = cache,
            pol: str = pol,
            loc: Callable[[float, float], dict[str, Any]] | None = loc,
        ) -> dict[str, Any]:
            key = (ws.label, subset)
            if key not in cache:
                cache[key], masks[pol][key] = _statistic(
                    arrays, [wins[o] for o in subset], min_tracks, cfg, loc
                )
            return cache[key]

        groups: dict[Subset, dict[str, Any]] = {}
        for ws in nulls:
            wins = usable(ws)
            subset = tuple(sorted(set(wins) & set(ev_tracks)))
            if len(subset) < min_tracks:
                continue
            null = stat(ws, wins, subset)
            g = groups.setdefault(subset, {"tracks": list(subset), "nulls": []})
            g["event"] = stat(event, ev_windows, subset)
            g["nulls"].append(
                {
                    "label": ws.label,
                    "after_dates": [wins[o].after.datetime_utc[:10] for o in subset],
                    **null,
                }
            )
        for subset in sorted(groups, key=lambda s: (-len(s), s)):
            g = groups[subset]
            g["summary"] = rank_summary(
                g["event"]["largest_patch_km2"], [n["largest_patch_km2"] for n in g["nulls"]]
            )
            pol_rec["groups"].append(g)
        pol_rec["event_by_track_set"] = {
            "+".join(map(str, sub)): stat(event, ev_windows, sub)
            for k in range(min_tracks, len(ev_tracks) + 1)
            for sub in combinations(ev_tracks, k)
        }
        pol_rec["status"] = "analysed"

    agreement = []
    km2_px = cfg.pixel_size_m**2 / 1e6
    if len(pols) >= 2:
        p1, p2 = pols[0], pols[1]
        for key in sorted(set(masks[p1]) & set(masks[p2])):
            m1, m2 = masks[p1][key], masks[p2][key]
            if m1.shape != m2.shape:
                continue
            union = int((m1 | m2).sum())
            agreement.append(
                {
                    "label": key[0],
                    "tracks": list(key[1]),
                    f"{p1}_km2": round(float(m1.sum()) * km2_px, 3),
                    f"{p2}_km2": round(float(m2.sum()) * km2_px, 3),
                    "shared_km2": round(float((m1 & m2).sum()) * km2_px, 3),
                    "jaccard": round(int((m1 & m2).sum()) / union, 4) if union else None,
                }
            )
    out["polarisation_agreement"] = agreement
    return out


class SceneSearcher(Protocol):
    def search(
        self, collection: str, bbox: Bbox, start: datetime, end: datetime
    ) -> tuple[list[SceneMeta], str | None]: ...


def seasonal_window_sets(
    client: SceneSearcher,
    collection: str,
    bbox: Bbox,
    event_utc: datetime,
    years_back: int,
    max_lag: int,
    min_gap_days: float,
    max_gap_days: float,
    search_before_days: int = 60,
    search_after_days: int = 14,
) -> tuple[WindowSet | None, list[WindowSet], dict[str, Any]]:
    """The event window, earlier cycles of the event year, and the same weeks in earlier years.

    Nulls from earlier years are placed on the same calendar date as the event, so they
    share its season, which is what makes them a fair comparison in terrain where snowmelt
    and monsoon drive most natural change. Every year uses the same cadence rules through
    ``cycle_windows``. Tracks are keyed by relative orbit number.
    """
    record: dict[str, Any] = {"years": {}}
    event: WindowSet | None = None
    nulls: list[WindowSet] = []
    for back in range(years_back + 1):
        year = event_utc.year - back
        anchor = event_utc.replace(year=year)
        scenes, err = client.search(
            collection,
            bbox,
            anchor - timedelta(days=search_before_days),
            anchor + timedelta(days=search_after_days),
        )
        rec: dict[str, Any] = {"anchor_utc": anchor.isoformat(), "passes": len(scenes)}
        record["years"][str(year)] = rec
        if err:
            rec["error"] = err
            continue
        per_track = cycle_windows(scenes, anchor, max_lag, max_gap_days, min_gap_days)
        by_lag: dict[int, dict[int, CycleWindow]] = {}
        for (orbit, _state), wins in per_track.items():
            for w in wins:
                by_lag.setdefault(w.lag, {})[orbit] = w
        rec["tracks_by_lag"] = {str(k): sorted(v) for k, v in sorted(by_lag.items())}
        for lag, lag_windows in sorted(by_lag.items()):
            if back == 0 and lag == 0:
                event = WindowSet(f"{year} lag 0", "event", lag_windows)
            else:
                nulls.append(WindowSet(f"{year} lag {lag}", "null", lag_windows))
    return event, nulls, record
