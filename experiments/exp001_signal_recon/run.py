"""Experiment 001 — signal reconnaissance on NK.KKN.

**Question.** Is the 26 August 2026 mass-movement signal present on Nepal's one open
broadband station, and does it separate from real earthquakes and from quiet noise?

**Design.** Four windows on NK.KKN.BHZ, analysis band 0.5-20 Hz:

1. the 26 August 2026 cascade;
2. two real regional earthquakes from the USGS catalogue, recorded on the same station;
3. a quiet-noise window at the same clock time one week before the event, which
   controls for diurnal cultural noise.

The earthquake windows are resolved from the USGS FDSN event service at run time rather
than hard-coded, so the comparison is reproducible rather than asserted.

**Re-running.** One command, from a cold cache:

    python experiments/exp001_signal_recon/run.py

First run fetches from EarthScope and populates ``data/cache``; subsequent runs are
offline and byte-identical. Results go to ``results.json``; findings are written by
hand into ``FINDINGS.md`` — including the negative ones. Experiments are immutable
once run: a new question gets a new experiment directory, never an edit to this one.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import (  # noqa: E402
    DEFAULT,
    NPT,
    PRIMARY_STATION,
    SOURCE_ZONE_LAT,
    SOURCE_ZONE_LON,
)
from ghadi.detect import sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import extract, preprocess  # noqa: E402

HERE = Path(__file__).parent
WINDOW_PRE_S = 600.0
WINDOW_POST_S = 1500.0

# The event under study (catalogue: NPL-2026-08-26-BHOTEKOSHI-001).
EVENT_UTC = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)


def _window(centre: datetime) -> tuple[datetime, datetime]:
    return centre - timedelta(seconds=WINDOW_PRE_S), centre + timedelta(seconds=WINDOW_POST_S)


REFERENCE_EVENTS_PATH = Path(__file__).parent / "reference_events.json"


def reference_earthquakes(limit: int = 2) -> list[dict[str, Any]]:
    """Resolve real regional earthquakes recorded on the same station.

    The resolved list is cached to ``reference_events.json`` and committed, because
    an experiment that re-queries a live catalogue on every run is not reproducible:
    a USGS outage, or a later revision to the catalogue, silently changes which
    events the comparison is made against. The cache is the record of what this
    experiment actually used.
    """
    if REFERENCE_EVENTS_PATH.exists():
        cached = json.loads(REFERENCE_EVENTS_PATH.read_text(encoding="utf-8"))
        return [
            {
                "origin_utc": datetime.fromisoformat(e["origin_utc"]),
                "magnitude": e["magnitude"],
                "label": "earthquake",
            }
            for e in cached["events"][:limit]
        ]

    from obspy.clients.fdsn import Client

    client = Client("USGS")
    catalog = client.get_events(
        starttime=__import__("obspy").UTCDateTime(EVENT_UTC - timedelta(days=60)),
        endtime=__import__("obspy").UTCDateTime(EVENT_UTC - timedelta(days=1)),
        latitude=SOURCE_ZONE_LAT,
        longitude=SOURCE_ZONE_LON,
        maxradius=4.0,
        minmagnitude=4.3,
    )
    events = []
    for event in catalog[:limit]:
        origin = event.preferred_origin() or event.origins[0]
        magnitude = event.preferred_magnitude() or event.magnitudes[0]
        events.append(
            {
                "origin_utc": origin.time.datetime.replace(tzinfo=UTC),
                "magnitude": float(magnitude.mag),
                "label": "earthquake",
            }
        )

    REFERENCE_EVENTS_PATH.write_text(
        json.dumps(
            {
                "resolved_utc": datetime.now(UTC).isoformat(),
                "query": {
                    "maxradius_deg": 4.0,
                    "minmagnitude": 4.3,
                    "centre": [SOURCE_ZONE_LAT, SOURCE_ZONE_LON],
                },
                "events": [
                    {"origin_utc": e["origin_utc"].isoformat(), "magnitude": e["magnitude"]}
                    for e in events
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return events


def analyse(
    name: str, label: str, centre: datetime, client: CachedWaveformClient
) -> dict[str, Any]:
    """Fetch one window and compute its features and baseline detector response."""
    start, end = _window(centre)
    request = WaveformRequest(
        PRIMARY_STATION.network,
        PRIMARY_STATION.station,
        PRIMARY_STATION.location,
        PRIMARY_STATION.channel,
        start,
        end,
    )
    result = client.get_waveforms(request)
    if not result.ok:
        return {"case": name, "label": label, "error": result.error}

    trace = result.stream.merge(fill_value="interpolate")[0]
    sampling_rate = float(trace.stats.sampling_rate)
    processed = preprocess(np.asarray(trace.data, dtype=float), sampling_rate)

    feats = extract(processed, sampling_rate, preprocessed=True)
    detection = sta_lta(processed, sampling_rate, preprocessed=True)

    trigger = detection.first_trigger
    onset_utc = None
    if trigger is not None:
        onset_utc = (start + timedelta(seconds=trigger.on_s)).isoformat()

    # SNR in dB: peak signal power over the pre-event noise floor.
    noise_samples = processed[: int(WINDOW_PRE_S * sampling_rate * 0.5)]
    noise_power = float(np.mean(noise_samples**2)) if noise_samples.size else float("nan")
    peak_power = float(np.max(processed**2))
    snr_db = 10.0 * np.log10(peak_power / noise_power) if noise_power > 0 else float("nan")

    return {
        "case": name,
        "label": label,
        "window_start_utc": start.isoformat(),
        "window_end_utc": end.isoformat(),
        "sampling_rate": sampling_rate,
        "n_samples": int(trace.stats.npts),
        "features": feats.as_dict(),
        "max_sta_lta": detection.max_ratio,
        "n_triggers": len(detection.triggers),
        "first_trigger_on_s": trigger.on_s if trigger else None,
        "first_trigger_duration_s": trigger.duration_s if trigger else None,
        "first_trigger_onset_utc": onset_utc,
        "snr_db": snr_db,
    }


def main() -> int:
    client = CachedWaveformClient()
    cases: list[dict[str, Any]] = []

    print("Case 1/4: 26 Aug 2026 Bhote Koshi cascade")
    cases.append(analyse("2026-08-26 Bhote Koshi", "mass_movement", EVENT_UTC, client))

    print("Resolving reference earthquakes from the USGS catalogue ...")
    try:
        for i, eq in enumerate(reference_earthquakes(), start=1):
            name = f"Reference EQ M{eq['magnitude']:.1f} {eq['origin_utc'].date()}"
            print(f"Case {i + 1}/4: {name}")
            cases.append(analyse(name, "earthquake", eq["origin_utc"], client))
    except Exception as exc:
        print(f"  reference-earthquake lookup failed: {exc}")
        cases.append({"case": "reference earthquakes", "label": "earthquake", "error": str(exc)})

    print("Case 4/4: quiet noise, same clock time one week earlier")
    cases.append(analyse("Quiet noise (T-7d)", "noise", EVENT_UTC - timedelta(days=7), client))

    results = {
        "experiment": "exp001_signal_recon",
        "run_utc": datetime.now(UTC).isoformat(),
        "station": PRIMARY_STATION.nslc,
        "config": {
            "band_hz": list(DEFAULT.seismic.band_hz),
            "sta_s": DEFAULT.seismic.sta_s,
            "lta_s": DEFAULT.seismic.lta_s,
            "trigger_on": DEFAULT.seismic.trigger_on,
            "trigger_off": DEFAULT.seismic.trigger_off,
            "spectral_split_hz": DEFAULT.seismic.spectral_split_hz,
        },
        "event_origin_utc": EVENT_UTC.isoformat(),
        "event_origin_npt": EVENT_UTC.astimezone(NPT).isoformat(),
        "cases": cases,
    }

    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {HERE / 'results.json'}")

    print(f"\n{'case':<34} {'label':<14} {'LF/HF':>8} {'centroid':>9} {'maxSTA/LTA':>11}")
    for case in cases:
        if "error" in case:
            print(f"{case['case']:<34} {case['label']:<14}  ERROR: {case['error']}")
            continue
        f = case["features"]
        print(
            f"{case['case']:<34} {case['label']:<14} "
            f"{f['spectral_ratio_low_high']:>8.2f} {f['spectral_centroid_hz']:>9.2f} "
            f"{case['max_sta_lta']:>11.2f}"
        )

    print("\nNow update FINDINGS.md by hand. Negative results are committed, not deleted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
