"""Experiment 015: is the 2026 radar signal extreme against the same weeks in earlier years?

**Question.** exp014 ranked the 2026 three-track agreement patch first among every clean
no-event window, but only three such windows existed, so its rank could not go below the
floor p = 0.25. It also had to compare against May and June windows for two tracks,
which are a different season. The natural fix is the same late August weeks in earlier
years, on the same tracks, in both polarisations. Is the event still the largest?

**Design.** ``ghadi.eo_null.seasonal_window_sets`` searches each year from 2022 to 2026
around 26 August and builds, per track, the window straddling that date (lag 0) and up
to three earlier cycles, all with 11 to 13 day gaps. The 2026 lag 0 window is the event;
every other window is a null. ``ghadi.eo_null.compare_event_to_nulls`` runs exp013's
cross-track test on each, compares like with like (each null against the event on the
same track set), and reports the empirical rank with its floor. Region, thresholds, and
tracks are exactly those of exp012 to exp014, and nothing was tuned after exp014.

**Before the run.** 2022 to 2024 had one Sentinel-1 satellite (12 day repeat); 2025 and
2026 had two sharing some tracks, whose 7 day windows are skipped by the cadence rule.

**Re-running.** The first run fetches and caches regions; later runs are offline:

    python experiments/exp015_seasonal_nulls_2026/run.py
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

EVENT = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)
SOURCE = (28.255, 85.520)
HALF_KM = 8.0
YEARS_BACK = 4
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
        "experiment": "exp015_seasonal_nulls_2026",
        "event_utc": EVENT.isoformat(),
        "source": {"lat": SOURCE[0], "lon": SOURCE[1]},
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
