"""Experiment 014: is the 2026 radar signal extreme against many no-event windows?

Checked in both radar polarisations.

**Question.** exp013 found a 0.41 km2 patch where at least two of three Sentinel-1
tracks agree on new change after 26 Aug 2026, 5.5x its null. But that null was one
pre-event cycle per track: a single point, not a distribution. And every radar result
so far used one polarisation (VV). Two questions:

1. **Null distribution.** Run the identical cross-track test on earlier acquisition
   cycles on the same ground and tracks, where no event happened. Where does the event
   window rank among them?
2. **Second polarisation.** Repeat everything in VH, which responds differently to
   surface roughness and volume scattering. Does VH independently show the event, and do
   VV and VH agree on WHERE more than they agree in no-event windows?

**Design.** One search, 170 days before to 14 days after the origin, over the same 16 km
box as exp012/013. ``ghadi.eo_fetch.cycle_windows`` builds, per track, the event window
(lag 0) and earlier windows (lag k), each as control-before / before / after passes.
Every gap must be 11 to 13 days: a missing acquisition stops the sequence, and a 7 day
window (a second satellite sharing the track in June and July) is skipped, because a
shorter window has less time for natural change and would make a softer null.

For each window: per-track change masks for the window and for its control, per-track
excess (changed in window, not in control), and ``ghadi.eo.cross_track_excess``. The
statistic is the largest connected patch where at least two tracks agree.

**Like with like.** Not every earlier window has all three tracks. "Two of two agree" is
a stricter bar than "two of three", so a two-track null is naturally smaller and would
flatter the event. Every null window is therefore compared with the event window
computed on exactly the same set of tracks, and results are grouped by that track set.
The empirical rank uses the (1 + count at or above the event) / (1 + n) convention.

**Caveat, stated before the run.** Most earlier windows fall in June and July, nearer peak
monsoon than the event window, so natural change is expected to be larger in the null.
That makes the test conservative against the event.

**Re-running.** The first run fetches and caches the regions; later runs are offline:

    python experiments/exp014_null_distribution_vh/run.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import DEFAULT  # noqa: E402
from ghadi.eo import cross_track_excess, sar_change_masks  # noqa: E402
from ghadi.eo_fetch import (  # noqa: E402
    SENTINEL1_RTC,
    CachedSceneClient,
    CycleWindow,
    RoiResult,
    SceneMeta,
    align_arrays,
    bbox_around,
    cycle_windows,
    transform_rowcol_to_lonlat,
)
from ghadi.geo import haversine_km  # noqa: E402

EVENT = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)
SOURCE = (28.255, 85.520)
HALF_KM = 8.0  # same region as exp012/013 for 2026
MAX_LAG = 12
MIN_GAP_DAYS = 11.0
MAX_GAP_DAYS = 13.0
SEARCH_BEFORE_DAYS = 170
MIN_TRACKS = 2
POLS = ("vv", "vh")
KM2_PER_PIXEL = DEFAULT.eo.pixel_size_m**2 / 1e6

Subset = tuple[int, ...]


def _brief(s: SceneMeta) -> dict[str, Any]:
    return {"item_id": s.item_id, "date": s.datetime_utc[:10], "orbit": s.relative_orbit}


def _statistic(
    arrays: dict[str, np.ndarray],
    windows: list[CycleWindow],
    common: Any,
    epsg: int,
) -> tuple[dict[str, Any], np.ndarray]:
    ev, ct, va = [], [], []
    for w in windows:
        b = arrays[w.before.item_id]
        a = arrays[w.after.item_id]
        c = arrays[w.control_before.item_id]
        e_change, _, _, e_valid = sar_change_masks(b, a, config=DEFAULT.eo)
        c_change, _, _, c_valid = sar_change_masks(c, b, config=DEFAULT.eo)
        ev.append(e_change)
        ct.append(c_change)
        va.append(e_valid & c_valid)
    res = cross_track_excess(ev, ct, va, DEFAULT.eo.pixel_size_m**2, MIN_TRACKS)
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
    if res.largest_patch_centroid_rc is not None:
        r0, c0 = res.largest_patch_centroid_rc
        lon, lat = transform_rowcol_to_lonlat(common, epsg, r0, c0)
        out["largest_patch_centroid"] = {"lat": round(lat, 4), "lon": round(lon, 4)}
        out["distance_from_source_km"] = round(haversine_km(*SOURCE, lat, lon), 2)
    return out, agree >= MIN_TRACKS


def _jaccard(m1: np.ndarray, m2: np.ndarray) -> float | None:
    union = int((m1 | m2).sum())
    return round(int((m1 & m2).sum()) / union, 4) if union else None


def main() -> None:
    client = CachedSceneClient()
    bbox = bbox_around(SOURCE[0], SOURCE[1], HALF_KM)
    scenes, err = client.search(
        SENTINEL1_RTC,
        bbox,
        EVENT - timedelta(days=SEARCH_BEFORE_DAYS),
        EVENT + timedelta(days=14),
    )
    results: dict[str, Any] = {
        "experiment": "exp014_null_distribution_vh",
        "event_utc": EVENT.isoformat(),
        "roi_half_km": HALF_KM,
        "max_lag": MAX_LAG,
        "min_gap_days": MIN_GAP_DAYS,
        "max_gap_days": MAX_GAP_DAYS,
        "search_before_days": SEARCH_BEFORE_DAYS,
        "min_tracks": MIN_TRACKS,
        "sar_change_db": DEFAULT.eo.sar_change_db,
        "speckle_filter_px": DEFAULT.eo.speckle_filter_px,
    }
    if err:
        results["status"] = "search_failed"
        results["reason"] = err
        _write(results)
        print("search failed:", err)
        return

    per_track = cycle_windows(scenes, EVENT, MAX_LAG, MAX_GAP_DAYS, MIN_GAP_DAYS)
    results["scenes_found"] = len(scenes)
    results["windows"] = {
        f"{orbit}_{state}": [
            {
                "lag": w.lag,
                "control_before": _brief(w.control_before),
                "before": _brief(w.before),
                "after": _brief(w.after),
            }
            for w in wins
        ]
        for (orbit, state), wins in per_track.items()
    }
    needed = {
        s.item_id: s
        for wins in per_track.values()
        for w in wins
        for s in (w.control_before, w.before, w.after)
    }
    print(f"{len(scenes)} passes, {len(needed)} regions needed per polarisation", flush=True)

    results["polarisations"] = {}
    masks: dict[str, dict[tuple[int, Subset], np.ndarray]] = {}

    for pol in POLS:
        print(f"\n=== {pol.upper()} ===", flush=True)
        rois: dict[str, RoiResult] = {}
        failures = []
        ordered = sorted(needed.items(), key=lambda kv: kv[1].when)
        for i, (item_id, scene) in enumerate(ordered):
            r = client.read_roi(scene, pol, bbox)
            print(
                f"  [{i + 1}/{len(needed)}] {scene.datetime_utc[:10]} o{scene.relative_orbit} "
                f"{'cache' if r.cache_hit else 'fetch'} {'ok' if r.ok else 'FAILED'}",
                flush=True,
            )
            if r.ok:
                rois[item_id] = r
            else:
                failures.append({"item_id": item_id, "error": r.error})
        ids = list(rois)
        aligned, common = align_arrays([rois[i] for i in ids])
        arrays = dict(zip(ids, aligned, strict=True))
        epsg = rois[ids[0]].epsg or 0

        # Usable windows per lag: every region of the window read successfully.
        by_lag: dict[int, dict[int, CycleWindow]] = {}
        for (orbit, _state), wins in per_track.items():
            for w in wins:
                if all(s.item_id in arrays for s in (w.control_before, w.before, w.after)):
                    by_lag.setdefault(w.lag, {})[orbit] = w
        event_tracks = tuple(sorted(by_lag.get(0, {})))

        cache: dict[tuple[int, Subset], dict[str, Any]] = {}
        pol_masks: dict[tuple[int, Subset], np.ndarray] = {}

        def stat(
            lag: int,
            subset: Subset,
            by_lag: dict[int, dict[int, CycleWindow]] = by_lag,
            arrays: dict[str, np.ndarray] = arrays,
            common: Any = common,
            epsg: int = epsg,
            cache: dict[tuple[int, Subset], dict[str, Any]] = cache,
            pol_masks: dict[tuple[int, Subset], np.ndarray] = pol_masks,
        ) -> dict[str, Any]:
            key = (lag, subset)
            if key not in cache:
                wins = [by_lag[lag][o] for o in subset]
                cache[key], pol_masks[key] = _statistic(arrays, wins, common, epsg)
            return cache[key]

        groups: dict[Subset, dict[str, Any]] = {}
        for lag in sorted(k for k in by_lag if k > 0):
            subset = tuple(sorted(set(by_lag[lag]) & set(event_tracks)))
            if len(subset) < MIN_TRACKS:
                continue
            null = stat(lag, subset)
            g = groups.setdefault(subset, {"tracks": list(subset), "nulls": []})
            g["event"] = stat(0, subset)
            g["nulls"].append(
                {
                    "lag": lag,
                    "after_dates": [by_lag[lag][o].after.datetime_utc[:10] for o in subset],
                    **null,
                }
            )
            print(
                f"  tracks {list(subset)} lag {lag}: null {null['largest_patch_km2']} km2 "
                f"(event on same tracks {g['event']['largest_patch_km2']} km2)",
                flush=True,
            )

        for g in groups.values():
            ev = g["event"]["largest_patch_km2"]
            vals = [n["largest_patch_km2"] for n in g["nulls"]]
            ge = sum(v >= ev for v in vals)
            g["summary"] = {
                "event_largest_km2": ev,
                "null_largest_km2": vals,
                "n_null": len(vals),
                "null_max_km2": max(vals),
                "null_median_km2": round(float(np.median(vals)), 4),
                "event_over_null_max": round(ev / max(vals), 2) if max(vals) > 0 else None,
                "null_windows_at_or_above_event": ge,
                "empirical_p": round((1 + ge) / (1 + len(vals)), 3),
            }

        event_all = {
            "+".join(map(str, sub)): stat(0, sub)
            for k in range(MIN_TRACKS, len(event_tracks) + 1)
            for sub in combinations(event_tracks, k)
        }
        ordered_groups = [groups[k] for k in sorted(groups, key=lambda s: (-len(s), s))]
        results["polarisations"][pol] = {
            "failures": failures,
            "grid_shape": list(aligned[0].shape),
            "event_tracks": list(event_tracks),
            "event_by_track_set": event_all,
            "groups": ordered_groups,
        }
        for g in ordered_groups:
            sm = g["summary"]
            print(
                f"  -> tracks {g['tracks']}: event {sm['event_largest_km2']} vs "
                f"{sm['n_null']} nulls (max {sm['null_max_km2']}, median "
                f"{sm['null_median_km2']}); p = {sm['empirical_p']}",
                flush=True,
            )
        masks[pol] = pol_masks
        del arrays, aligned, rois

    # VV and VH agreement on WHERE, for the same window and the same track set.
    agreement = []
    for key in sorted(set(masks.get("vv", {})) & set(masks.get("vh", {}))):
        lag, subset = key
        m1, m2 = masks["vv"][key], masks["vh"][key]
        if m1.shape != m2.shape:
            continue
        agreement.append(
            {
                "lag": lag,
                "role": "event" if lag == 0 else "null",
                "tracks": list(subset),
                "vv_km2": round(float(m1.sum()) * KM2_PER_PIXEL, 3),
                "vh_km2": round(float(m2.sum()) * KM2_PER_PIXEL, 3),
                "shared_km2": round(float((m1 & m2).sum()) * KM2_PER_PIXEL, 3),
                "jaccard": _jaccard(m1, m2),
            }
        )
    results["vv_vh_agreement"] = agreement
    results["status"] = "analysed"
    _write(results)


def _write(results: dict[str, Any]) -> None:
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nresults -> {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
