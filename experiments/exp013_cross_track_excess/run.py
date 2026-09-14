"""Experiment 013: do independent radar tracks agree on WHERE the ground changed?

**Question.** exp012 confirmed the 2026 source with a coarse statistic: the largest
changed patch anywhere in a 16 km box, judged against a same-track control. Its
weakness is stated there: the largest patch can be a river reach or a glacier tongue.
Does the excess sit in the same pixels on all three viewing geometries, and is that
agreement larger than the same test gives for a window with no event in it?

**Design.** Everything is offline, from exp012's cached regions. For each event and
each track, form the per-pixel radar change mask for the event pair and for the
pre-event control pair (same 3 dB rule, same median filter). A track's *excess* is a
pixel changed in the event pair and not in its control. Summing excess over tracks
gives, per pixel, how many independent geometries saw new change there; the statistic
is the largest connected patch where at least two agree. The **null** swaps the roles
on the same data: pixels changed only in the pre-event window. If the method is sound,
the event window's agreement patch should stand well clear of the null's.

**Re-running.** Fully cached; runs with the network forbidden:

    GHADI_OFFLINE=1 python experiments/exp013_cross_track_excess/run.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import DEFAULT  # noqa: E402
from ghadi.eo import cross_track_excess, sar_change_masks  # noqa: E402
from ghadi.eo_fetch import (  # noqa: E402
    SENTINEL1_RTC,
    CachedSceneClient,
    RoiResult,
    SceneMeta,
    align_arrays,
    bbox_around,
    transform_rowcol_to_lonlat,
)
from ghadi.geo import haversine_km  # noqa: E402

EXP012 = REPO_ROOT / "experiments" / "exp012_satellite_confirmation" / "results.json"
MIN_TRACKS = 2
ASSET = "vv"


def _scene(brief: dict[str, Any]) -> SceneMeta:
    # The cache key uses only item_id, asset and region, so the date is informational.
    return SceneMeta(
        item_id=brief["item_id"],
        collection=SENTINEL1_RTC,
        datetime_utc=f"{brief['date']}T00:00:00Z",
        relative_orbit=brief.get("orbit"),
        orbit_state=None,
        cloud_cover=None,
    )


def _read(client: CachedSceneClient, brief: dict[str, Any], bbox: Any) -> RoiResult:
    return client.read_roi(_scene(brief), ASSET, bbox)


def run_event(client: CachedSceneClient, ev: dict[str, Any]) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "event_id": ev["event_id"],
        "catalogued_location": ev["catalogued_location"],
        "location_uncertainty_km": ev.get("location_uncertainty_km"),
    }
    if ev.get("status") != "analysed":
        rec["status"] = ev.get("status")
        rec["reason"] = ev.get("reason", "")
        return rec
    lat, lon = ev["catalogued_location"]["lat"], ev["catalogued_location"]["lon"]
    bbox = bbox_around(lat, lon, ev["roi_half_km"])

    tracks: list[dict[str, Any]] = []
    rois: list[RoiResult] = []
    for p in ev["pairs"]:
        if "error" in p or not p.get("control"):
            continue
        reads = [
            _read(client, p["before"], bbox),
            _read(client, p["after"], bbox),
            _read(client, p["control"]["before"], bbox),
        ]
        if not all(r.ok for r in reads):
            rec.setdefault("skipped_tracks", []).append(
                {"orbit": p["before"]["orbit"], "error": next(r.error for r in reads if r.error)}
            )
            continue
        tracks.append({"orbit": p["before"]["orbit"], "reads": reads})
        rois.extend(reads)
    if len(tracks) < MIN_TRACKS:
        rec["status"] = "too_few_tracks"
        rec["reason"] = f"{len(tracks)} usable track(s); need {MIN_TRACKS}"
        return rec

    try:
        arrays, common = align_arrays(rois)
    except ValueError as exc:
        rec["status"] = "grids_differ"
        rec["reason"] = str(exc)
        return rec
    px_area = DEFAULT.eo.pixel_size_m**2
    epsg = rois[0].epsg or 0

    event_masks, control_masks, valids = [], [], []
    per_track: list[dict[str, Any]] = []
    for i, t in enumerate(tracks):
        before, after, ctrl_before = arrays[3 * i], arrays[3 * i + 1], arrays[3 * i + 2]
        e_change, _, _, e_valid = sar_change_masks(before, after, config=DEFAULT.eo)
        c_change, _, _, c_valid = sar_change_masks(ctrl_before, before, config=DEFAULT.eo)
        valid = e_valid & c_valid
        event_masks.append(e_change)
        control_masks.append(c_change)
        valids.append(valid)
        per_track.append(
            {
                "orbit": t["orbit"],
                "event_change_km2": round(float((e_change & valid).sum()) * px_area / 1e6, 3),
                "control_change_km2": round(float((c_change & valid).sum()) * px_area / 1e6, 3),
            }
        )

    def summarise(result: Any, label: str) -> dict[str, Any]:
        by_k = {str(k): round(v, 3) for k, v in result.area_km2_by_agreement.items()}
        out: dict[str, Any] = {
            "largest_patch_km2": round(result.largest_patch_km2, 3),
            "area_km2_by_agreement": by_k,
            "per_track_excess_km2": [round(v, 3) for v in result.per_track_excess_km2],
        }
        if result.largest_patch_centroid_rc is not None:
            r, c = result.largest_patch_centroid_rc
            blon, blat = transform_rowcol_to_lonlat(common, epsg, r, c)
            out["largest_patch_centroid"] = {"lat": round(blat, 4), "lon": round(blon, 4)}
            out["distance_from_source_km"] = round(haversine_km(lat, lon, blat, blon), 2)
        print(f"  {label}: {result.reason}", flush=True)
        return out

    event = cross_track_excess(event_masks, control_masks, valids, px_area, MIN_TRACKS)
    null = cross_track_excess(control_masks, event_masks, valids, px_area, MIN_TRACKS)
    rec["status"] = "analysed"
    rec["n_tracks"] = len(tracks)
    rec["grid_shape"] = list(arrays[0].shape)
    rec["per_track"] = per_track
    rec["event_window"] = summarise(event, "event window (changed in event pair only)")
    rec["null_window"] = summarise(null, "null window   (changed in control pair only)")
    e_l, n_l = event.largest_patch_km2, null.largest_patch_km2
    rec["event_over_null_ratio"] = round(e_l / n_l, 2) if n_l > 0 else None
    return rec


def main() -> None:
    data = json.loads(EXP012.read_text(encoding="utf-8"))
    client = CachedSceneClient()
    results: dict[str, Any] = {
        "experiment": "exp013_cross_track_excess",
        "source": "exp012 cached regions",
        "min_tracks": MIN_TRACKS,
        "sar_change_db": DEFAULT.eo.sar_change_db,
        "speckle_filter_px": DEFAULT.eo.speckle_filter_px,
        "events": [],
    }
    for ev in data["events"]:
        print()
        print(f"=== {ev['event_id']} ===", flush=True)
        rec = run_event(client, ev)
        results["events"].append(rec)
        if rec["status"] != "analysed":
            print(f"  status: {rec['status']} {rec.get('reason', '')}")
            continue
        ew, nw = rec["event_window"], rec["null_window"]
        print(
            f"  largest >= {MIN_TRACKS}-track patch: event {ew['largest_patch_km2']} km2 "
            f"({ew.get('distance_from_source_km', 'n/a')} km from source) vs null "
            f"{nw['largest_patch_km2']} km2 -> ratio {rec['event_over_null_ratio']}"
        )
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print()
    print(f"results -> {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
