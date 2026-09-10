"""Experiment 012 — can radar imagery confirm the 2026 source, and find the other events?

**Question.** The positive class is one event (n=1). Seismic detection gives the WHEN;
it cannot by itself prove WHERE the ground failed. Free Sentinel-1 radar sees through
monsoon cloud and revisits every 12 days per track. Does a before/after comparison show
a changed patch at the catalogued 2026 source zone, and does the same method find the
other catalogue candidates whose times and places are only known from news reports?

**Design.** For each event, search Sentinel-1 RTC scenes from 40 days before to 30 days
after the origin, and form same-track pairs (last scene before, first scene after, on
the same relative orbit and pass direction; different tracks are never compared). Read
only the region of interest (VV backscatter) and run ``ghadi.eo.detect_change_sar``.
For every event pair, also run a **control pair** on the same track from before the
event, so that seasonal river change on the same ground is measured rather than assumed
away. A "change detected" that is not larger than its control is not a confirmation.
The comparison is explicit and recorded per pair (``ghadi.eo.compare_to_control``): an
event pair counts as *above background* only if its largest changed patch is at least
2.0 times the control's. That ratio was fixed before the 2026 pair was inspected, so it
could not be tuned to the answer.

**What this cannot say.** The imagery bounds the event between two acquisition dates;
it does not give the minute. Confirming a patch at a candidate confirms WHERE, and
narrows WHEN to a 12-day window, which is what a labelled window needs.

**Re-running.** One command; the first run fetches and caches regions from the
Planetary Computer, later runs are offline and byte-identical:

    python experiments/exp012_satellite_confirmation/run.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import DEFAULT  # noqa: E402
from ghadi.eo import detect_change_sar  # noqa: E402
from ghadi.eo_fetch import (  # noqa: E402
    SENTINEL1_RTC,
    SENTINEL1_START,
    CachedSceneClient,
    SceneMeta,
    bbox_around,
    rowcol_to_lonlat,
    same_track_pairs,
)
from ghadi.geo import haversine_km  # noqa: E402

CATALOG_DIR = REPO_ROOT / "data" / "catalog"
SEARCH_BEFORE_DAYS = 40
SEARCH_AFTER_DAYS = 30
MAX_GAP_DAYS = 30
ASSET = "vv"


def _aware(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def load_events() -> list[dict[str, Any]]:
    events = []
    for path in sorted(CATALOG_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        events.append(
            {
                "event_id": raw["event_id"],
                "origin_utc": _aware(raw["origin_utc"]),
                "lat": float(raw["lat"]),
                "lon": float(raw["lon"]),
                "location_uncertainty_km": float(raw.get("location_uncertainty_km", 5.0)),
                "hazard_subtype": raw.get("hazard_subtype", ""),
            }
        )
    return events


def _scene_brief(s: SceneMeta) -> dict[str, Any]:
    return {"item_id": s.item_id, "date": s.datetime_utc[:10], "orbit": s.relative_orbit}


def analyse_pair(
    client: CachedSceneClient,
    before: SceneMeta,
    after: SceneMeta,
    bbox: tuple[float, float, float, float],
    source_lat: float,
    source_lon: float,
) -> dict[str, Any]:
    b = client.read_roi(before, ASSET, bbox)
    a = client.read_roi(after, ASSET, bbox)
    out: dict[str, Any] = {
        "before": _scene_brief(before),
        "after": _scene_brief(after),
        "gap_days": round((after.when - before.when).total_seconds() / 86400.0, 1),
        "cache_hits": [b.cache_hit, a.cache_hit],
    }
    if not (b.ok and a.ok):
        out["error"] = b.error or a.error
        return out
    assert b.array is not None and a.array is not None
    if b.array.shape != a.array.shape:
        out["error"] = f"shape mismatch {b.array.shape} vs {a.array.shape}"
        return out
    res = detect_change_sar(b.array, a.array, b.pixel_area_m2, config=DEFAULT.eo)
    out.update(
        {
            "verdict": res.verdict,
            "valid_fraction": round(res.valid_fraction, 3),
            "changed_fraction": round(res.changed_fraction, 4),
            "changed_area_km2": round(res.changed_area_km2, 3),
            "n_blobs": res.n_blobs,
            "largest_blob_km2": round(res.largest_blob_km2, 3),
            "decrease_fraction": round(res.decrease_fraction, 4),
            "increase_fraction": round(res.increase_fraction, 4),
            "reason": res.reason,
        }
    )
    if res.largest_blob_centroid_rc is not None:
        r, c = res.largest_blob_centroid_rc
        lon, lat = rowcol_to_lonlat(b, r, c)
        out["largest_blob_centroid"] = {"lat": round(lat, 4), "lon": round(lon, 4)}
        out["blob_distance_from_source_km"] = round(
            haversine_km(source_lat, source_lon, lat, lon), 2
        )
    return out


def control_for(scenes: list[SceneMeta], before: SceneMeta) -> SceneMeta | None:
    """The previous acquisition cycle on the same track, never a frame of the same pass.

    Two frames of one pass share a date and near-identical imagery over their overlap;
    comparing them would give a control with almost no change and inflate the event
    against it. The first run of this experiment did exactly that on Thame 2024, which
    is why the rule now lives in ``ghadi.eo_fetch.previous_pass``.
    """
    from ghadi.eo_fetch import previous_pass

    return previous_pass(scenes, before)


def run_event(client: CachedSceneClient, ev: dict[str, Any]) -> dict[str, Any]:
    origin: datetime = ev["origin_utc"]
    record: dict[str, Any] = {
        "event_id": ev["event_id"],
        "origin_utc": origin.isoformat(),
        "hazard_subtype": ev["hazard_subtype"],
        "catalogued_location": {"lat": ev["lat"], "lon": ev["lon"]},
        "location_uncertainty_km": ev["location_uncertainty_km"],
    }
    if origin < SENTINEL1_START:
        record["status"] = "no_scene"
        record["reason"] = "predates the Sentinel-1 archive (October 2014)"
        return record

    half = max(DEFAULT.eo.roi_half_km, ev["location_uncertainty_km"])
    bbox = bbox_around(ev["lat"], ev["lon"], half)
    record["roi_half_km"] = half
    scenes, err = client.search(
        SENTINEL1_RTC,
        bbox,
        origin - timedelta(days=SEARCH_BEFORE_DAYS),
        origin + timedelta(days=SEARCH_AFTER_DAYS),
    )
    if err:
        record["status"] = "search_failed"
        record["reason"] = err
        return record
    record["scenes_found"] = len(scenes)
    pairs = same_track_pairs(scenes, origin, MAX_GAP_DAYS)
    if not pairs:
        record["status"] = "no_pair"
        record["reason"] = "no same-track before/after pair within the gap limit"
        return record

    record["status"] = "analysed"
    record["pairs"] = []
    for before, after in pairs:
        print(
            f"    pair orbit {before.relative_orbit}: {before.datetime_utc[:10]} -> "
            f"{after.datetime_utc[:10]}",
            flush=True,
        )
        entry = analyse_pair(client, before, after, bbox, ev["lat"], ev["lon"])
        ctrl = control_for(scenes, before)
        if ctrl is not None:
            print(
                f"    control orbit {ctrl.relative_orbit}: {ctrl.datetime_utc[:10]} -> "
                f"{before.datetime_utc[:10]}",
                flush=True,
            )
            entry["control"] = analyse_pair(client, ctrl, before, bbox, ev["lat"], ev["lon"])
        else:
            entry["control"] = None
        ctrl_rec = entry.get("control")
        if ctrl_rec and "verdict" in entry and "verdict" in ctrl_rec:
            from ghadi.eo import compare_to_control

            comparison = compare_to_control(
                entry["verdict"],
                entry["largest_blob_km2"],
                ctrl_rec["verdict"],
                ctrl_rec["largest_blob_km2"],
                config=DEFAULT.eo,
            )
            entry["control_comparison"] = dict(vars(comparison))
        record["pairs"].append(entry)
    return record


def main() -> None:
    client = CachedSceneClient()
    results: dict[str, Any] = {
        "experiment": "exp012_satellite_confirmation",
        "collection": SENTINEL1_RTC,
        "asset": ASSET,
        "config": {
            "roi_half_km_min": DEFAULT.eo.roi_half_km,
            "sar_change_db": DEFAULT.eo.sar_change_db,
            "speckle_filter_px": DEFAULT.eo.speckle_filter_px,
            "min_valid_fraction": DEFAULT.eo.min_valid_fraction,
            "min_blob_km2": DEFAULT.eo.min_blob_km2,
            "search_window_days": [SEARCH_BEFORE_DAYS, SEARCH_AFTER_DAYS],
            "max_gap_days": MAX_GAP_DAYS,
        },
        "events": [],
    }
    for ev in load_events():
        print(f"\n=== {ev['event_id']} ===", flush=True)
        rec = run_event(client, ev)
        results["events"].append(rec)
        print(f"  status: {rec['status']}" + (f" ({rec['reason']})" if "reason" in rec else ""))
        for p in rec.get("pairs", []):
            if "error" in p:
                print(f"  {p['before']['date']} -> {p['after']['date']}: ERROR {p['error']}")
                continue
            ctrl = p.get("control") or {}
            print(
                f"  orbit {p['before']['orbit']} {p['before']['date']} -> {p['after']['date']}"
                f" ({p['gap_days']} d): {p['verdict']}, largest {p['largest_blob_km2']} km2,"
                f" {p.get('blob_distance_from_source_km', 'n/a')} km from source"
                f" | control: {ctrl.get('verdict', 'none')},"
                f" largest {ctrl.get('largest_blob_km2', 'n/a')} km2"
                f" | vs control: {(p.get('control_comparison') or {}).get('verdict', 'n/a')}"
            )

    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nresults -> {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
