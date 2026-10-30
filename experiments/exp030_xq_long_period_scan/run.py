"""Experiment 030: are there uncatalogued slope failures in the 2015 to 2016 network data?

**Question.** The positive class is one event, and nothing in the catalogue has added a
second. From June 2015 to May 2016 a temporary network (XQ) had eighteen stations with
long period channels across central Nepal, the nearest 14 km from the 2026 source, in
the year after the Gorkha earthquake when many slopes failed. exp029 showed that a large
mass movement carries strong energy below 0.1 Hz, where small local earthquakes carry
little. Does a scan of that band across the network turn up events that no earthquake
catalogue explains and that look local?

**Design.**

* **Data.** The 1 sample per second vertical channel (LHZ) of the twelve stations with
  that channel within about 100 km of the 2026 source, for the whole deployment.
* **Per station.** Band pass 0.02 to 0.08 Hz, envelope smoothed over 60 s, divided by
  that day's median envelope. The result is "how many times the ordinary level".
* **Across the network.** In every 10 s step, the number of stations at 4 times their
  ordinary level within a minute either side. A candidate is a run of steps where at
  least four stations, and at least half of those reporting, agree.
* **Catalogued earthquakes.** A candidate whose peak falls in the phase window of a
  catalogued earthquake is explained: M5.0 and above anywhere, M4.5 and above within
  45 degrees, or M4.0 and above within 20 degrees. The windows are those of ``ghadi.teleseism``.
* **Local or distant.** A distant source arrives at a 100 km network with nearly the
  same strength everywhere. A local one is far stronger at the nearest station. The
  contrast is the strongest station's ratio over the median of the rest.

The output is a list of unexplained candidates, ranked, with the strongest station for
each. It is a list of things to look at, not a list of slope failures: an uncatalogued
local earthquake, an instrument glitch on several stations, or a storm would all appear
here, and each candidate needs its short period record and an outside report before it
means anything.

    python experiments/exp030_xq_long_period_scan/run.py
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.basin import load_basin  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402
from ghadi.origins_feed import parse_usgs_csv  # noqa: E402
from ghadi.teleseism import Origin, epicentral_distance_deg, phase_window  # noqa: E402

HERE = Path(__file__).resolve().parent
SOURCE = (28.255, 85.520)
STATIONS = {  # code: (lat, lon), LHZ, nearest first
    "NA080": (28.271, 85.379),
    "NA100": (27.928, 85.555),
    "NA090": (27.915, 85.419),
    "NA110": (27.798, 85.654),
    "NA130": (27.878, 85.891),
    "NA170": (27.758, 85.362),
    "NA010": (27.837, 85.151),
    "NA020": (27.913, 85.055),
    "NA050": (28.057, 84.834),
    "NA040": (28.205, 84.744),
    "NA210": (27.739, 86.158),
    "NA250": (27.776, 84.650),
}
START = datetime(2015, 6, 25, tzinfo=UTC)
END = datetime(2016, 5, 10, tzinfo=UTC)
CHUNK_DAYS = 10
BAND = (0.02, 0.08)
STEP_S = 10
SMOOTH_S = 60
LEVEL = 4.0
MIN_STATIONS = 4
COINCIDENCE_S = 60
MERGE_GAP_S = 300
LOCAL_CONTRAST = 3.0
CATALOGUE = HERE / "catalogue.json"
USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def fetch_catalogue() -> list[Origin]:
    """M5.0 anywhere, M4.5 within 45 degrees, and M4.0 within 20 degrees, for the period."""
    if CATALOGUE.exists():
        raw = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    else:
        raw = []
        seen: set[str] = set()
        cursor = START - timedelta(hours=3)
        while cursor < END:
            stop = min(cursor + timedelta(days=60), END)
            for extra in (
                {"minmagnitude": "5.0"},
                {
                    "minmagnitude": "4.5",
                    "latitude": str(SOURCE[0]),
                    "longitude": str(SOURCE[1]),
                    "maxradius": "45",
                },
                {
                    "minmagnitude": "4.0",
                    "latitude": str(SOURCE[0]),
                    "longitude": str(SOURCE[1]),
                    "maxradius": "20",
                },
            ):
                params = {
                    "format": "csv",
                    "starttime": cursor.strftime("%Y-%m-%dT%H:%M:%S"),
                    "endtime": stop.strftime("%Y-%m-%dT%H:%M:%S"),
                    "orderby": "time-asc",
                    **extra,
                }
                url = f"{USGS}?{urllib.parse.urlencode(params)}"
                with urllib.request.urlopen(url, timeout=60) as response:
                    for o in parse_usgs_csv(response.read().decode("utf-8")):
                        if o.event_id in seen:
                            continue
                        seen.add(o.event_id)
                        raw.append(
                            {
                                "time_utc": o.time_utc.isoformat(),
                                "latitude": o.latitude,
                                "longitude": o.longitude,
                                "magnitude": o.magnitude,
                                "event_id": o.event_id,
                                "place": o.place,
                            }
                        )
            cursor = stop
        CATALOGUE.write_text(json.dumps(raw), encoding="utf-8")
    return [
        Origin(
            datetime.fromisoformat(r["time_utc"]),
            r["latitude"],
            r["longitude"],
            r["magnitude"],
            r.get("event_id", ""),
            r.get("place", ""),
        )
        for r in raw
    ]


def station_ratio(client: CachedWaveformClient, code: str, n_steps: int) -> np.ndarray:
    """Envelope over the day's median, on the common 10 s grid. NaN where no data."""
    out = np.full(n_steps, np.nan, dtype=np.float32)
    sos = butter(4, BAND, btype="bandpass", fs=1.0, output="sos")
    cursor = START
    while cursor < END:
        stop = min(cursor + timedelta(days=CHUNK_DAYS), END)
        r = client.get_waveforms(WaveformRequest("XQ", code, "", "LHZ", cursor, stop))
        if r.ok:
            for tr in r.stream:
                if abs(tr.stats.sampling_rate - 1.0) > 1e-6 or tr.stats.npts < 3600:
                    continue
                x = np.asarray(tr.data, dtype=float)
                x = x - np.mean(x)
                env = np.abs(hilbert(sosfiltfilt(sos, x)))
                env = np.convolve(env, np.ones(SMOOTH_S) / SMOOTH_S, mode="same")
                t0 = tr.stats.starttime.datetime.replace(tzinfo=UTC)
                offset = (t0 - START).total_seconds()
                day_len = 86400
                for a in range(0, env.size, day_len):
                    seg = env[a : a + day_len]
                    if seg.size < 3600:
                        continue
                    med = float(np.median(seg))
                    if med <= 0:
                        continue
                    ratio = seg / med
                    n_bins = seg.size // STEP_S
                    binned = ratio[: n_bins * STEP_S].reshape(n_bins, STEP_S).max(axis=1)
                    first = int((offset + a) // STEP_S)
                    lo, hi = max(first, 0), min(first + n_bins, n_steps)
                    if hi > lo:
                        out[lo:hi] = binned[lo - first : hi - first]
        cursor = stop
    return out


def rolling_max(x: np.ndarray, half: int) -> np.ndarray:
    filled = np.nan_to_num(x, nan=0.0)
    out = filled.copy()
    for k in range(1, half + 1):
        out[k:] = np.maximum(out[k:], filled[:-k])
        out[:-k] = np.maximum(out[:-k], filled[k:])
    return out


def main() -> int:
    client = CachedWaveformClient()
    basin = load_basin()
    n_steps = int((END - START).total_seconds() // STEP_S)
    codes = list(STATIONS)
    ratios = np.empty((len(codes), n_steps), dtype=np.float32)
    for i, code in enumerate(codes):
        ratios[i] = station_ratio(client, code, n_steps)
        have = float(np.mean(~np.isnan(ratios[i])))
        print(f"   {code}: data for {have:.0%} of the period", flush=True)

    available = (~np.isnan(ratios)).sum(axis=0)
    half = COINCIDENCE_S // STEP_S
    near = np.stack([rolling_max(r, half) for r in ratios])
    hot = (near >= LEVEL).sum(axis=0)
    flag = (hot >= MIN_STATIONS) & (hot >= 0.5 * available) & (available >= MIN_STATIONS)

    # Merge flagged steps into candidates.
    idx = np.flatnonzero(flag)
    candidates: list[tuple[int, int]] = []
    if idx.size:
        start = prev = int(idx[0])
        gap = MERGE_GAP_S // STEP_S
        for j in idx[1:]:
            j = int(j)
            if j - prev > gap:
                candidates.append((start, prev))
                start = j
            prev = j
        candidates.append((start, prev))

    origins = fetch_catalogue()
    centre = (
        float(np.mean([v[0] for v in STATIONS.values()])),
        float(np.mean([v[1] for v in STATIONS.values()])),
    )
    windows = []
    for o in origins:
        deg = epicentral_distance_deg(centre[0], centre[1], o)
        if (
            o.magnitude >= 5.0
            or (o.magnitude >= 4.5 and deg <= 45.0)
            or (o.magnitude >= 4.0 and deg <= 20.0)
        ):
            opens, closes, _ = phase_window(o, centre[0], centre[1])
            windows.append((opens, closes, o))
    windows.sort(key=lambda w: w[0])
    opens_ts = np.array([w[0].timestamp() for w in windows])

    def explained(when: datetime) -> Origin | None:
        k = int(np.searchsorted(opens_ts, when.timestamp(), side="right"))
        for opens, closes, o in windows[max(k - 400, 0) : k]:
            if opens <= when <= closes:
                return o
        return None

    rows: list[dict[str, Any]] = []
    for a, b in candidates:
        seg = np.nan_to_num(ratios[:, a : b + 1], nan=0.0)
        peak_step = a + int(np.argmax(seg.sum(axis=0)))
        when = START + timedelta(seconds=peak_step * STEP_S)
        per = {
            codes[i]: float(np.nanmax(ratios[i, max(a - half, 0) : b + half + 1]))
            for i in range(len(codes))
            if np.isfinite(ratios[i, a : b + 1]).any()
        }
        if len(per) < MIN_STATIONS:
            continue
        ordered = sorted(per.items(), key=lambda kv: -kv[1])
        strongest, top = ordered[0]
        rest = [v for _, v in ordered[1:]]
        contrast = top / float(np.median(rest)) if rest else float("nan")
        origin = explained(when)
        lat, lon = STATIONS[strongest]
        rows.append(
            {
                "peak_utc": when.isoformat(),
                "duration_s": (b - a + 1) * STEP_S,
                "stations_reporting": len(per),
                "stations_above_level": int(sum(v >= LEVEL for v in per.values())),
                "strongest_station": strongest,
                "strongest_ratio": round(top, 1),
                "median_of_rest": round(float(np.median(rest)), 1) if rest else None,
                "contrast": round(contrast, 2),
                "strongest_station_in_catchment": bool(basin.contains(lat, lon)[0]),
                "strongest_station_km_from_2026_source": round(haversine_km(lat, lon, *SOURCE), 1),
                "explained_by": None
                if origin is None
                else {
                    "magnitude": origin.magnitude,
                    "place": origin.place,
                    "time_utc": origin.time_utc.isoformat(),
                    "distance_deg": round(epicentral_distance_deg(centre[0], centre[1], origin), 1),
                },
                "ratios": {k: round(v, 1) for k, v in ordered},
            }
        )

    unexplained = [r for r in rows if r["explained_by"] is None]
    local = [r for r in unexplained if r["contrast"] >= LOCAL_CONTRAST]
    local.sort(key=lambda r: -r["strongest_ratio"])
    big_quakes = [w for w in windows if w[2].magnitude >= 6.0]
    caught = sum(
        1
        for opens, closes, _ in big_quakes
        if any(opens <= datetime.fromisoformat(r["peak_utc"]) <= closes for r in rows)
    )
    results = {
        "experiment": "exp030_xq_long_period_scan",
        "period": [START.isoformat(), END.isoformat()],
        "stations": {k: {"lat": v[0], "lon": v[1]} for k, v in STATIONS.items()},
        "band_hz": list(BAND),
        "level": LEVEL,
        "min_stations": MIN_STATIONS,
        "station_days": round(float((~np.isnan(ratios)).sum()) * STEP_S / 86400.0, 1),
        "catalogue_origins": len(origins),
        "candidates": len(rows),
        "explained_by_catalogue": len(rows) - len(unexplained),
        "unexplained": len(unexplained),
        "unexplained_local": len(local),
        "sanity_m6_plus": {"catalogued": len(big_quakes), "seen_as_candidates": caught},
        "local_candidates": local[:60],
        "unexplained_distant_like": sorted(
            (r for r in unexplained if r["contrast"] < LOCAL_CONTRAST),
            key=lambda r: -r["strongest_ratio"],
        )[:30],
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"station days scanned: {results['station_days']}")
    print(
        f"candidates {len(rows)}; explained {results['explained_by_catalogue']}; "
        f"unexplained {len(unexplained)}; of those local {len(local)}"
    )
    print(f"sanity: {caught} of {len(big_quakes)} catalogued M6+ earthquakes are candidates")
    for r in local[:25]:
        print(
            f"   {r['peak_utc'][:19]} {r['strongest_station']} "
            f"ratio {r['strongest_ratio']:7.1f} rest {r['median_of_rest']:5.1f} "
            f"contrast {r['contrast']:6.1f} dur {r['duration_s']:5d}s "
            f"in catchment {r['strongest_station_in_catchment']}"
        )
    print(f"results -> {(HERE / 'results.json').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
