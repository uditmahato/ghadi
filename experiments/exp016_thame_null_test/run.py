"""Experiment 016: does the Thame 2024 radar lead survive a proper null test?

**Question.** Thame (16 Aug 2024, a glacial lake outburst) is the only older catalogue
event that looked promising from orbit: in exp012 two tracks put their largest patch
within 0.3 km of each other, and in exp013 the cross-track patch was 2.4x its single null.
Both are weak on their own. Does Thame rank above a distribution of like-for-like no-event
windows, in both polarisations, the way 2026 did in exp014 and exp015?

**Design.** Identical to exp015, pointed at Thame. The region is centred on the
catalogued point (27.870 N, 86.620 E) with the catalogued 6 km uncertainty as its half
width, the same region exp012 and exp013 used. It is deliberately not recentred on the
spot those experiments flagged, because choosing the region from the data and then
testing inside it would be circular. Nulls are the earlier cycles of 2024 and the same
weeks of 2021 to 2023, with the same cadence rules and thresholds. Nothing was tuned for
Thame.

**Before the run.** 2021 had two Sentinel-1 satellites on a 6 day repeat until December,
so its windows are expected to fail the 11 to 13 day cadence rule and yield no nulls.
That will be recorded, not worked around.

**Re-running.** The first run fetches and caches regions; later runs are offline:

    python experiments/exp016_thame_null_test/run.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import DEFAULT  # noqa: E402
from ghadi.eo_fetch import (  # noqa: E402
    SENTINEL1_RTC,
    CachedSceneClient,
    bbox_around,
    transform_rowcol_to_lonlat,
)
from ghadi.eo_null import compare_event_to_nulls, seasonal_window_sets  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402

EVENT = datetime(2024, 8, 16, 8, 0, 0, tzinfo=UTC)
SOURCE = (27.870, 86.620)
FLAGGED_SPOT = (27.856, 86.564)  # where exp012 and exp013 pointed; reported, not used
HALF_KM = 6.0
YEARS_BACK = 3
MAX_LAG = 3
MIN_GAP_DAYS = 11.0
MAX_GAP_DAYS = 13.0
SEARCH_BEFORE_DAYS = 75
SEARCH_AFTER_DAYS = 14


def locate(transform: Any, epsg: int, row: float, col: float) -> dict[str, Any]:
    lon, lat = transform_rowcol_to_lonlat(transform, epsg, row, col)
    return {
        "largest_patch_centroid": {"lat": round(lat, 4), "lon": round(lon, 4)},
        "distance_from_source_km": round(haversine_km(*SOURCE, lat, lon), 2),
        "distance_from_flagged_spot_km": round(haversine_km(*FLAGGED_SPOT, lat, lon), 2),
    }


def main() -> None:
    client = CachedSceneClient()
    bbox = bbox_around(SOURCE[0], SOURCE[1], HALF_KM)
    event, nulls, windows = seasonal_window_sets(
        client,
        SENTINEL1_RTC,
        bbox,
        EVENT,
        YEARS_BACK,
        MAX_LAG,
        MIN_GAP_DAYS,
        MAX_GAP_DAYS,
        SEARCH_BEFORE_DAYS,
        SEARCH_AFTER_DAYS,
    )
    results: dict[str, Any] = {
        "experiment": "exp016_thame_null_test",
        "event_utc": EVENT.isoformat(),
        "source": {"lat": SOURCE[0], "lon": SOURCE[1]},
        "flagged_spot": {"lat": FLAGGED_SPOT[0], "lon": FLAGGED_SPOT[1]},
        "roi_half_km": HALF_KM,
        "years_back": YEARS_BACK,
        "max_lag": MAX_LAG,
        "min_gap_days": MIN_GAP_DAYS,
        "max_gap_days": MAX_GAP_DAYS,
        "sar_change_db": DEFAULT.eo.sar_change_db,
        "speckle_filter_px": DEFAULT.eo.speckle_filter_px,
        "windows": windows,
        "null_labels": [n.label for n in nulls],
    }
    print(json.dumps(windows, indent=1), flush=True)
    if event is None:
        results["status"] = "no_event_window"
        _write(results)
        return
    print(f"event tracks {sorted(event.windows)}; {len(nulls)} null windows", flush=True)
    results.update(compare_event_to_nulls(client, bbox, event, nulls, locate=locate))
    results["status"] = "analysed"
    for pol, rec in results["polarisations"].items():
        for g in rec.get("groups", []):
            sm = g["summary"]
            print(
                f"{pol} tracks {g['tracks']}: event {sm['event_largest_km2']} km2 vs "
                f"{sm['n_null']} nulls (max {sm['null_max_km2']}, median "
                f"{sm['null_median_km2']}); at or above {sm['null_windows_at_or_above_event']}; "
                f"p = {sm['empirical_p']} (floor {sm['p_floor']})",
                flush=True,
            )
    _write(results)


def _write(results: dict[str, Any]) -> None:
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"results -> {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
