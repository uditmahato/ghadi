"""Fetch the global earthquake catalogue used for teleseism suppression (exp004).

exp004 found that half the detector's false alarms were distant earthquakes. Attenuation
strips their high frequencies, so they arrive looking exactly like a slow extended
source and are not separable on the spectral features. The only reliable discriminant is
external: a global catalogue.

This fetches origins once and caches them, for the same reason every other catalogue in
this repository is cached — a corpus whose definition depends on a live service quietly
changes when that service is revised.

Uses the raw USGS endpoint rather than ObsPy's client: ObsPy discovers server
capabilities at construction time and intermittently reports "this client does not have
an event service" while the raw endpoint answers HTTP 200 seconds later.

    python scripts/harvest_global_catalogue.py
    python scripts/harvest_global_catalogue.py --start 2024-01-01 --end 2026-08-02
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "data" / "corpus" / "global_catalogue.json"
ENDPOINT = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def fetch_chunk(
    start: datetime, end: datetime, min_magnitude: float, attempts: int = 5
) -> list[dict[str, Any]]:
    params = {
        "format": "geojson",
        "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end.strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": str(min_magnitude),
        "orderby": "time",
    }
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                payload = json.loads(response.read().decode())
            return payload.get("features", [])
        except Exception as exc:
            print(f"    attempt {attempt}/{attempts}: {type(exc).__name__}", flush=True)
            if attempt < attempts:
                time.sleep(8 * attempt)
    raise RuntimeError(f"global catalogue query failed for {start:%Y-%m-%d}..{end:%Y-%m-%d}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-08-02")
    parser.add_argument("--min-magnitude", type=float, default=5.5)
    args = parser.parse_args(argv)

    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)

    origins: list[dict[str, Any]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=120), end)
        print(f"  {cursor:%Y-%m-%d} .. {chunk_end:%Y-%m-%d}", flush=True)
        for feature in fetch_chunk(cursor, chunk_end, args.min_magnitude):
            props = feature["properties"]
            lon, lat, _depth = feature["geometry"]["coordinates"]
            origins.append(
                {
                    "event_id": feature.get("id", ""),
                    "time_utc": datetime.fromtimestamp(props["time"] / 1000, tz=UTC).isoformat(),
                    "latitude": lat,
                    "longitude": lon,
                    "magnitude": props["mag"],
                    "place": props.get("place") or "",
                }
            )
        cursor = chunk_end

    # De-duplicate across chunk boundaries.
    seen: set[str] = set()
    unique = []
    for origin in origins:
        key = origin["event_id"] or origin["time_utc"]
        if key not in seen:
            seen.add(key)
            unique.append(origin)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "resolved_utc": datetime.now(UTC).isoformat(),
                "purpose": (
                    "teleseism suppression: distant earthquakes are not separable "
                    "from mass movements on the spectral features (exp004)"
                ),
                "query": {
                    "service": "USGS FDSN event (raw endpoint)",
                    "scope": "global",
                    "min_magnitude": args.min_magnitude,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                },
                "count": len(unique),
                "origins": unique,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n{len(unique)} global M>={args.min_magnitude} origins -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
