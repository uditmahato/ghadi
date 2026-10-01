"""Experiment 029: can a lower frequency band see this kind of event from further away?

**Question.** The detector works in 0.5 to 20 Hz and did not see the Chamoli 2021 rock
and ice avalanche at 610 km (exp023). Published detections of such events use long
period energy. Is Chamoli visible at NK.KKN in a lower band, is the 2026 event visible
there too, and how often does ordinary noise look the same?

**Design.**

* **Bands.** The working band (0.5 to 20 Hz) and three lower ones: 0.1 to 0.5 Hz,
  0.05 to 0.1 Hz, and 0.02 to 0.05 Hz.
* **Statistic.** For an origin time and distance, the surface wave window is where a
  wave travelling 2.5 to 4.5 km/s arrives. The statistic is the peak of the smoothed
  envelope in that window over the median envelope of the ten minutes before the
  origin. It is a signal to noise ratio that needs no trigger.
* **Events.** Chamoli 2021 at NK.KKN (610 km). The 2026 event at NK.KKN (56 km) and
  IO.EVN (131 km), for reference.
* **Noise.** The same statistic at the same window geometry in 150 windows of the
  same station's noise corpus, which contain no catalogued M5.5 earthquake. The share of noise
  windows at or above an event's value is its empirical rank.

A low band is where distant earthquakes live, so a visible signal here would still
have to be told apart from them. This experiment only asks whether there is anything
to tell apart.

    python experiments/exp029_low_frequency_band/run.py
"""

from __future__ import annotations

import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import EVEREST, KAKANI, StationSite  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402

CORPUS = REPO_ROOT / "data" / "corpus" / "noise.json"
BANDS = {
    "0.5-20 Hz": (0.5, 20.0),
    "0.1-0.5 Hz": (0.1, 0.5),
    "0.05-0.1 Hz": (0.05, 0.1),
    "0.02-0.05 Hz": (0.02, 0.05),
}
V_FAST, V_SLOW = 4.5, 2.5
PRE_S, POST_S = 600.0, 2100.0
N_NOISE = 150
SEED = 29
EVENTS = [
    ("Chamoli 2021", KAKANI, datetime(2021, 2, 7, 4, 51, 0, tzinfo=UTC), (30.375, 79.732)),
    ("Bhote Koshi 2026", KAKANI, datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC), (28.255, 85.520)),
    ("Bhote Koshi 2026", EVEREST, datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC), (28.255, 85.520)),
]


def load(
    client: CachedWaveformClient, site: StationSite, start: datetime, end: datetime
) -> tuple[np.ndarray | None, float]:
    r = client.get_waveforms(
        WaveformRequest(
            site.site.network, site.site.station, site.site.location, site.site.channel, start, end
        )
    )
    if not r.ok:
        return None, 0.0
    tr = r.stream.merge(fill_value="interpolate")[0]
    return np.asarray(tr.data, dtype=float), float(tr.stats.sampling_rate)


def band_snr(
    data: np.ndarray, sr: float, band: tuple[float, float], origin_s: float, distance_km: float
) -> float | None:
    lo, hi = band
    hi = min(hi, 0.45 * sr)
    x = data - np.mean(data)
    sos = butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos")
    y = sosfiltfilt(sos, x)
    env = np.abs(hilbert(y))
    smooth = max(int(sr * 2.0 / lo), 1)  # two periods of the lowest frequency
    kernel = np.ones(smooth) / smooth
    env = np.convolve(env, kernel, mode="same")
    a = int((origin_s + distance_km / V_FAST) * sr)
    b = int((origin_s + distance_km / V_SLOW + 120.0) * sr)
    n0 = int(max(origin_s - 540.0, 30.0) * sr)
    n1 = int((origin_s - 30.0) * sr)
    if b > env.size or n1 - n0 < sr * 60 or b - a < sr * 5:
        return None
    noise = float(np.median(env[n0:n1]))
    if noise <= 0:
        return None
    return float(np.max(env[a:b]) / noise)


def main() -> int:
    client = CachedWaveformClient()
    results: dict[str, Any] = {
        "experiment": "exp029_low_frequency_band",
        "bands": BANDS,
        "events": [],
        "noise": {},
    }
    geometries: dict[tuple[str, float], dict[str, list[float]]] = {}

    noise_by_site: dict[str, list[tuple[np.ndarray, float]]] = {}

    def noise_for(site: StationSite) -> list[tuple[np.ndarray, float]]:
        """Noise windows recorded at the same station as the event being ranked."""
        if site.key in noise_by_site:
            return noise_by_site[site.key]
        path = CORPUS if site.key == "NK.KKN" else CORPUS.with_name("noise_IO_EVN.json")
        corpus = json.loads(path.read_text(encoding="utf-8"))
        ok = [w for w in corpus["windows"] if w["status"] == "ok"]
        random.Random(SEED).shuffle(ok)
        windows: list[tuple[np.ndarray, float]] = []
        for w in ok:
            if len(windows) >= N_NOISE:
                break
            start = datetime.fromisoformat(w["window_start_utc"])
            data, sr = load(client, site, start, start + timedelta(seconds=corpus["window_s"]))
            if data is not None and data.size >= sr * 2000:
                windows.append((data, sr))
        print(f"{len(windows)} noise windows at {site.key}")
        noise_by_site[site.key] = windows
        return windows

    for name, site, origin, source in EVENTS:
        distance = haversine_km(site.latitude, site.longitude, *source)
        data, sr = load(
            client, site, origin - timedelta(seconds=PRE_S), origin + timedelta(seconds=POST_S)
        )
        rec: dict[str, Any] = {
            "event": name,
            "station": site.key,
            "distance_km": round(distance, 1),
        }
        if data is None:
            rec["status"] = "no_waveform"
            results["events"].append(rec)
            print(f"{name} at {site.key}: no waveform")
            continue
        rec["status"] = "ok"
        rec["bands"] = {}
        geo = (site.key, distance)
        if geo not in geometries:
            geometries[geo] = {
                b: [
                    v
                    for d, s in noise_for(site)
                    if (v := band_snr(d, s, lim, PRE_S, distance)) is not None
                ]
                for b, lim in BANDS.items()
            }
        for bname, lim in BANDS.items():
            snr = band_snr(data, sr, lim, PRE_S, distance)
            null = geometries[geo][bname]
            ge = sum(1 for v in null if snr is not None and v >= snr)
            rec["bands"][bname] = {
                "snr": None if snr is None else round(snr, 2),
                "noise_median": round(float(np.median(null)), 2) if null else None,
                "noise_p95": round(float(np.percentile(null, 95)), 2) if null else None,
                "noise_max": round(float(np.max(null)), 2) if null else None,
                "noise_windows": len(null),
                "noise_at_or_above": ge,
                "empirical_p": round((1 + ge) / (1 + len(null)), 4)
                if null and snr is not None
                else None,
            }
        results["events"].append(rec)
        print(f"{name} at {site.key}, {distance:.0f} km")
        for bname, b in rec["bands"].items():
            print(
                f"   {bname:<13} snr {b['snr']}  noise median {b['noise_median']} "
                f"p95 {b['noise_p95']} max {b['noise_max']}  p {b['empirical_p']}"
            )
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
