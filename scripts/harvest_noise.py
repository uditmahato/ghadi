"""Issue 1.3 — harvest a continuous-noise corpus, stratified by season and hour.

The noise corpus is what makes a false-alarm rate measurable. Without it there is no
denominator, and "the detector fired on the cascade" is an anecdote rather than a
result.

**Stratification is the scientific content, not bookkeeping.** Nepal's cultural and
environmental noise varies strongly by hour (traffic, human activity) and by season
(monsoon rain, river discharge, wind). A corpus sampled without stratification would be
dominated by whatever period happened to be convenient, and a model trained against it
could reach a good score by learning "monsoon afternoons are noisy" — a shortcut that
has nothing to do with mass movements and that collapses the moment it meets a dry-day
event like 26 August 2026.

**Windows containing catalogued earthquakes are excluded and counted.** A "noise" window
holding a real earthquake is a mislabelled positive, and it inflates the apparent false
alarm rate while teaching the model that events are non-events. The exclusions are
reported, because how many there are is itself informative about the region's rate.

    python scripts/harvest_noise.py --per-cell 4
    python scripts/harvest_noise.py --report
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

from ghadi.config import PRIMARY_STATION, SOURCE_ZONE_LAT, SOURCE_ZONE_LON  # noqa: E402
from ghadi.detect import sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import extract, preprocess  # noqa: E402

MANIFEST = REPO_ROOT / "data" / "corpus" / "noise.json"

# A full year, so every season is represented, ending before the 2026 cascade.
PERIOD_START = datetime(2025, 8, 1, tzinfo=UTC)
PERIOD_END = datetime(2026, 8, 1, tzinfo=UTC)

WINDOW_S = 2100.0  # same length as the event windows, so features are comparable
# Hours sampled (UTC). NPT is UTC+05:45, so 00 UTC is ~05:45 local: these six cells
# span pre-dawn, morning, midday, afternoon, evening and night in local time.
HOURS_UTC = (0, 4, 8, 12, 16, 20)
# Guard around a catalogued earthquake: a window overlapping this is not noise.
EVENT_GUARD_S = 3600.0


def catalogued_events(min_magnitude: float, max_radius_deg: float) -> list[datetime]:
    """Origin times of catalogued earthquakes that could contaminate a noise window."""
    from obspy import UTCDateTime
    from obspy.clients.fdsn import Client

    client = Client("USGS", timeout=120)
    catalog = client.get_events(
        starttime=UTCDateTime(PERIOD_START - timedelta(seconds=EVENT_GUARD_S)),
        endtime=UTCDateTime(PERIOD_END + timedelta(seconds=EVENT_GUARD_S)),
        latitude=SOURCE_ZONE_LAT,
        longitude=SOURCE_ZONE_LON,
        maxradius=max_radius_deg,
        minmagnitude=min_magnitude,
    )
    out = []
    for event in catalog:
        origin = event.preferred_origin() or event.origins[0]
        out.append(origin.time.datetime.replace(tzinfo=UTC))
    return sorted(out)


def candidate_windows(per_cell: int, seed: int) -> list[datetime]:
    """Sample window starts stratified over (month, hour-of-day) cells."""
    rng = np.random.default_rng(seed)
    starts: list[datetime] = []

    month = datetime(PERIOD_START.year, PERIOD_START.month, 1, tzinfo=UTC)
    while month < PERIOD_END:
        # Days available in this month, within the period.
        next_month = (month.replace(day=28) + timedelta(days=8)).replace(day=1)
        for hour in HOURS_UTC:
            for _ in range(per_cell):
                span_days = (min(next_month, PERIOD_END) - month).days
                if span_days <= 0:
                    continue
                day = int(rng.integers(0, span_days))
                start = month + timedelta(days=day, hours=hour)
                if PERIOD_START <= start < PERIOD_END:
                    starts.append(start)
        month = next_month

    return sorted(set(starts))


def contaminated(start: datetime, events: list[datetime]) -> datetime | None:
    """Return the catalogued event contaminating this window, if any."""
    end = start + timedelta(seconds=WINDOW_S)
    guard = timedelta(seconds=EVENT_GUARD_S)
    for origin in events:
        if start - guard <= origin <= end + guard:
            return origin
    return None


def process(start: datetime, client: CachedWaveformClient) -> dict[str, Any]:
    end = start + timedelta(seconds=WINDOW_S)
    row: dict[str, Any] = {
        "window_start_utc": start.isoformat(),
        "window_end_utc": end.isoformat(),
        "month": start.month,
        "hour_utc": start.hour,
    }

    result = client.get_waveforms(
        WaveformRequest(
            PRIMARY_STATION.network,
            PRIMARY_STATION.station,
            PRIMARY_STATION.location,
            PRIMARY_STATION.channel,
            start,
            end,
        )
    )
    if not result.ok:
        row["status"] = "no_waveform"
        row["reason"] = result.error
        return row

    try:
        trace = result.stream.merge(fill_value="interpolate")[0]
        sr = float(trace.stats.sampling_rate)
        proc = preprocess(np.asarray(trace.data, dtype=float), sr)
        detection = sta_lta(proc, sr, preprocessed=True)
        features = extract(proc, sr, preprocessed=True)
    except Exception as exc:
        row["status"] = "processing_failed"
        row["reason"] = f"{type(exc).__name__}: {exc}"
        return row

    row["n_samples"] = int(trace.stats.npts)
    row["n_triggers"] = len(detection.triggers)
    row["max_sta_lta"] = detection.max_ratio
    row["signal_present"] = features.signal_present
    row["features"] = features.as_dict()
    row["status"] = "ok"
    return row


def harvest(
    per_cell: int, seed: int, min_magnitude: float, max_radius_deg: float
) -> dict[str, Any]:
    print(
        f"Fetching catalogue to exclude contaminated windows (M>={min_magnitude}) ...", flush=True
    )
    events = catalogued_events(min_magnitude, max_radius_deg)
    print(f"  {len(events)} catalogued events in the period\n", flush=True)

    starts = candidate_windows(per_cell, seed)
    print(
        f"{len(starts)} candidate windows over {len(HOURS_UTC)} hour cells x 12 months\n",
        flush=True,
    )

    client = CachedWaveformClient()
    rows = []
    for i, start in enumerate(starts, start=1):
        origin = contaminated(start, events)
        if origin is not None:
            rows.append(
                {
                    "window_start_utc": start.isoformat(),
                    "month": start.month,
                    "hour_utc": start.hour,
                    "status": "excluded_catalogued_event",
                    "reason": f"catalogued event at {origin.isoformat()} within guard",
                }
            )
            continue
        rows.append(process(start, client))
        if i % 10 == 0:
            ok = sum(1 for r in rows if r["status"] == "ok")
            print(f"  [{i}/{len(starts)}] {ok} usable so far", flush=True)

    return {
        "created_utc": datetime.now(UTC).isoformat(),
        "station": PRIMARY_STATION.nslc,
        "label": "noise",
        "period": {"start": PERIOD_START.isoformat(), "end": PERIOD_END.isoformat()},
        "stratification": {"hours_utc": list(HOURS_UTC), "per_cell": per_cell, "seed": seed},
        "window_s": WINDOW_S,
        "event_guard_s": EVENT_GUARD_S,
        "windows": rows,
    }


def report(manifest: dict[str, Any]) -> None:
    rows = manifest["windows"]
    statuses = Counter(r["status"] for r in rows)
    usable = [r for r in rows if r["status"] == "ok"]

    total_hours = len(usable) * manifest["window_s"] / 3600.0
    print(f"\nNoise corpus: {len(rows)} candidate windows, {len(usable)} usable")
    print(f"  {total_hours:.1f} hours of continuous noise")
    for status, count in statuses.most_common():
        print(f"  {status:<28} {count:>4}")

    if not usable:
        return

    print("\nBy month (stratification check):")
    by_month = Counter(r["month"] for r in usable)
    for month in range(1, 13):
        print(f"  {month:>2}: {'#' * by_month.get(month, 0)} ({by_month.get(month, 0)})")

    print("\nBy hour UTC:")
    by_hour = Counter(r["hour_utc"] for r in usable)
    for hour in sorted(by_hour):
        print(f"  {hour:02d}: {'#' * by_hour[hour]} ({by_hour[hour]})")

    triggered = [r for r in usable if r["n_triggers"] > 0]
    print(
        f"\nWindows with at least one STA/LTA trigger: {len(triggered)}/{len(usable)}"
        f"\n  These are the baseline's false alarms. At {manifest['window_s'] / 3600:.2f} h"
        f" per window this is the raw material for a per-station-month rate (issue 5.3)."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-cell", type=int, default=4, help="windows per month-hour cell")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--min-magnitude", type=float, default=3.5)
    parser.add_argument("--max-radius-deg", type=float, default=6.0)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)

    if args.report:
        if not MANIFEST.exists():
            print(f"No manifest at {MANIFEST}. Run without --report first.")
            return 1
        report(json.loads(MANIFEST.read_text(encoding="utf-8")))
        return 0

    manifest = harvest(args.per_cell, args.seed, args.min_magnitude, args.max_radius_deg)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nWrote {MANIFEST}")
    report(manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
