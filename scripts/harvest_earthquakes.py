"""Issue 1.2 — harvest a reference-earthquake corpus on NK.KKN.

Queries the USGS catalogue for regional earthquakes within reach of NK.KKN, fetches a
window around each, and writes a manifest recording what was retrieved and what was not.

**Three things this does deliberately.**

*It records failures.* An event whose waveform is missing, or whose window contains no
trigger matching the catalogue origin, stays in the manifest with a reason. A corpus
that silently drops what it could not process misreports its own completeness, and the
gaps are rarely random — they correlate with distance, magnitude and station downtime,
which are exactly the things a detector's performance also depends on.

*It picks onsets by causality, not by "first trigger".* exp002 found a window whose
first trigger preceded the catalogued origin by 276 s: an unrelated transient that would
have been measured as if it were the labelled earthquake. See ``ghadi.detect.onset``.

*It records epicentral distance for every event.* exp002 showed onset-to-peak features
track the S-P interval, which grows with distance. Without distance in the manifest,
distance-stratified evaluation is impossible later.

    python scripts/harvest_earthquakes.py --limit 150
    python scripts/harvest_earthquakes.py --report
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import (  # noqa: E402
    SOURCE_ZONE_LAT,
    SOURCE_ZONE_LON,
    STATION_SITES,
    StationSite,
)
from ghadi.detect import pick_onset, sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import extract, preprocess  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402

# Stop before the 2026 cascade so the corpus cannot contain the target event.
CATALOGUE_END = datetime(2026, 8, 25, tzinfo=UTC)

WINDOW_PRE_S = 600.0
WINDOW_POST_S = 1500.0


def manifest_path(site: StationSite) -> Path:
    """NK.KKN keeps the original filename; other stations get a suffixed one, so a
    per-station corpus never overwrites another. Rates and features are per station
    (exp007), so the corpora must stay separate on disk too."""
    corpus = REPO_ROOT / "data" / "corpus"
    if site.site.station == "KKN" and site.site.network == "NK":
        return corpus / "earthquakes.json"
    return corpus / f"earthquakes_{site.site.network}_{site.site.station}.json"


def query_catalogue(
    site: StationSite, limit: int, min_magnitude: float, max_radius_deg: float
) -> list[dict[str, Any]]:
    """Fetch candidate events from USGS, nearest-in-time first.

    Distance is to *this* station: the same earthquake is nearer NK.KKN than IO.EVN,
    and the features track distance, so distance must be recomputed per station
    rather than reused from another corpus."""
    import time

    from obspy import UTCDateTime
    from obspy.clients.fdsn import Client

    # USGS service discovery and connections reset intermittently — the same fault the
    # noise harvester retries around. A transient reset must not lose a whole harvest.
    catalog = None
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            client = Client("USGS", timeout=120)
            catalog = client.get_events(
                starttime=UTCDateTime(site.archive_start),
                endtime=UTCDateTime(CATALOGUE_END),
                latitude=SOURCE_ZONE_LAT,
                longitude=SOURCE_ZONE_LON,
                maxradius=max_radius_deg,
                minmagnitude=min_magnitude,
                limit=limit,
            )
            break
        except Exception as exc:
            last_error = exc
            print(f"  catalogue attempt {attempt}/5 failed: {type(exc).__name__}", flush=True)
            if attempt < 5:
                time.sleep(15 * attempt)
    if catalog is None:
        raise RuntimeError("USGS event query failed after 5 attempts") from last_error

    events = []
    for event in catalog:
        origin = event.preferred_origin() or event.origins[0]
        magnitude = event.preferred_magnitude() or event.magnitudes[0]
        origin_utc = origin.time.datetime.replace(tzinfo=UTC)
        lat, lon = float(origin.latitude), float(origin.longitude)
        events.append(
            {
                "event_id": str(event.resource_id).split("/")[-1],
                "origin_utc": origin_utc.isoformat(),
                "magnitude": float(magnitude.mag),
                "magnitude_type": str(magnitude.magnitude_type or "unknown"),
                "lat": lat,
                "lon": lon,
                "depth_km": float(origin.depth or 0.0) / 1000.0,
                "distance_km": haversine_km(site.latitude, site.longitude, lat, lon),
            }
        )
    return events


def process(
    event: dict[str, Any], site: StationSite, client: CachedWaveformClient
) -> dict[str, Any]:
    """Fetch one event's window, pick its onset, and extract features."""
    origin = datetime.fromisoformat(event["origin_utc"])
    start = origin - timedelta(seconds=WINDOW_PRE_S)
    end = origin + timedelta(seconds=WINDOW_POST_S)

    row = dict(event)
    row["window_start_utc"] = start.isoformat()
    row["window_end_utc"] = end.isoformat()

    result = client.get_waveforms(
        WaveformRequest(
            site.site.network,
            site.site.station,
            site.site.location,
            site.site.channel,
            start,
            end,
        )
    )
    if not result.ok:
        row["status"] = "no_waveform"
        row["reason"] = result.error
        return row

    try:
        stream = result.stream.merge(fill_value="interpolate")
        trace = stream[0]
        sr = float(trace.stats.sampling_rate)
        row["n_samples"] = int(trace.stats.npts)
        row["sampling_rate"] = sr

        proc = preprocess(np.asarray(trace.data, dtype=float), sr)
        detection = sta_lta(proc, sr, preprocessed=True)
    except Exception as exc:
        row["status"] = "processing_failed"
        row["reason"] = f"{type(exc).__name__}: {exc}"
        return row

    pick = pick_onset(
        detection.triggers,
        origin_offset_s=WINDOW_PRE_S,
        distance_km=event["distance_km"],
    )
    row["n_triggers"] = len(detection.triggers)
    row["max_sta_lta"] = detection.max_ratio
    row["onset_reason"] = pick.reason
    row["n_rejected_before_origin"] = pick.n_rejected_before_origin

    if not pick.ok:
        row["status"] = "no_matching_onset"
        row["reason"] = pick.reason
        return row

    row["onset_s"] = pick.onset_s
    features = extract(proc, sr, preprocessed=True, onset_s=pick.onset_s)
    row["features"] = features.as_dict()
    row["signal_present"] = features.signal_present
    row["status"] = "ok"
    return row


def harvest(
    site: StationSite, limit: int, min_magnitude: float, max_radius_deg: float
) -> dict[str, Any]:
    print(
        f"Harvesting {site.nslc}: M>={min_magnitude}, within {max_radius_deg} deg, "
        f"limit {limit} ..."
    )
    events = query_catalogue(site, limit, min_magnitude, max_radius_deg)
    print(f"  {len(events)} candidate events\n")

    client = CachedWaveformClient()
    rows = []
    for i, event in enumerate(events, start=1):
        row = process(event, site, client)
        rows.append(row)
        if i % 10 == 0 or row["status"] != "ok":
            print(
                f"  [{i}/{len(events)}] M{event['magnitude']:.1f} "
                f"{event['origin_utc'][:10]} {event['distance_km']:>6.0f} km -> {row['status']}"
            )

    return {
        "created_utc": datetime.now(UTC).isoformat(),
        "station": site.nslc,
        "station_lat_lon": [site.latitude, site.longitude],
        "query": {
            "service": "USGS FDSN event",
            "centre": [SOURCE_ZONE_LAT, SOURCE_ZONE_LON],
            "max_radius_deg": max_radius_deg,
            "min_magnitude": min_magnitude,
            "starttime": site.archive_start.isoformat(),
            "endtime": CATALOGUE_END.isoformat(),
            "limit": limit,
        },
        "window": {"pre_s": WINDOW_PRE_S, "post_s": WINDOW_POST_S},
        "label": "earthquake",
        "events": rows,
    }


def report(manifest: dict[str, Any]) -> None:
    rows = manifest["events"]
    statuses = Counter(r["status"] for r in rows)
    usable = [r for r in rows if r["status"] == "ok"]

    print(f"\nCorpus: {len(rows)} candidate events, {len(usable)} usable")
    for status, count in statuses.most_common():
        print(f"  {status:<22} {count:>4}")

    if not usable:
        return

    print("\nUsable events by distance:")
    bins = [(0, 100), (100, 200), (200, 300), (300, 400), (400, 10_000)]
    for lo, hi in bins:
        n = sum(1 for r in usable if lo <= r["distance_km"] < hi)
        label = f"{lo}-{hi} km" if hi < 10_000 else f"{lo}+ km"
        print(f"  {label:<14} {n:>4}")

    print("\nUsable events by magnitude:")
    for lo in (4.0, 4.5, 5.0, 5.5, 6.0):
        hi = lo + 0.5
        n = sum(1 for r in usable if lo <= r["magnitude"] < hi)
        print(f"  M{lo}-{hi:<10} {n:>4}")

    rejected = sum(r.get("n_rejected_before_origin", 0) for r in rows)
    affected = sum(1 for r in rows if r.get("n_rejected_before_origin", 0) > 0)
    print(
        f"\nPre-origin triggers rejected: {rejected} across {affected} window(s). "
        "\n  Each one would have been measured as the labelled event under a "
        "\n  first-trigger rule (exp002)."
    )

    lf = [r["features"]["spectral_ratio_low_high"] for r in usable]
    centroid = [r["features"]["spectral_centroid_hz"] for r in usable]
    if lf:
        print("\nSpectral features over the usable corpus (earthquakes):")
        print(
            f"  LF/HF     median {np.median(lf):.2f}  "
            f"p10 {np.percentile(lf, 10):.2f}  p90 {np.percentile(lf, 90):.2f}"
        )
        print(
            f"  centroid  median {np.median(centroid):.2f} Hz  "
            f"p10 {np.percentile(centroid, 10):.2f}  p90 {np.percentile(centroid, 90):.2f}"
        )
        print("\n  For comparison, the 26 Aug 2026 cascade: LF/HF 4.14, centroid 2.04 Hz")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=150)
    parser.add_argument("--min-magnitude", type=float, default=4.0)
    parser.add_argument("--max-radius-deg", type=float, default=4.0)
    parser.add_argument(
        "--station",
        default="NK.KKN",
        choices=sorted(STATION_SITES),
        help="which station's corpus to harvest (default NK.KKN)",
    )
    parser.add_argument("--report", action="store_true", help="report on the existing manifest")
    args = parser.parse_args(argv)

    site = STATION_SITES[args.station]
    path = manifest_path(site)

    if args.report:
        if not path.exists():
            print(f"No manifest at {path}. Run without --report first.")
            return 1
        report(json.loads(path.read_text(encoding="utf-8")))
        return 0

    manifest = harvest(site, args.limit, args.min_magnitude, args.max_radius_deg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nWrote {path}")
    report(manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
