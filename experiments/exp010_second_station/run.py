"""Experiment 010 — does the spectral separation reproduce on a second station?

**The question this settles.** exp003 and exp005 measured the cascade's separation from
earthquakes on NK.KKN. A real objection remained: is that separation a property of the
*source physics* (a slow extended source is low-frequency, wherever you stand), or a
property of *NK.KKN's site* (its response, its local noise, its geology)? One station
cannot tell the two apart.

IO.EVN is an independent station 131 km from the source — different site, different
response, different distance. If the cascade still sits at the low-frequency edge of
IO.EVN's earthquake population, the separation is source physics. If it does not, the
NK.KKN result was a site effect and the project's premise is in trouble.

**Method.** exactly exp005's, on IO.EVN: 120 s decision-time segments from the picked
onset (exp005 established that as the only operationally realisable basis), for both the
cascade and every usable earthquake in the IO.EVN corpus (exp007's second station,
harvested via ``harvest_earthquakes.py --station IO.EVN``).

The cascade window on IO.EVN is fetched once, then cached. Everything else reads the
committed manifest and the waveform cache — offline after the first run.

    python experiments/exp010_second_station/run.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import EVEREST  # noqa: E402
from ghadi.detect import pick_onset, sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import preprocess, spectral_features  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402


def _rank_corr(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


HERE = Path(__file__).parent
IO_EVN_CORPUS = REPO_ROOT / "data" / "corpus" / "earthquakes_IO_EVN.json"

CASCADE_ORIGIN = datetime.fromisoformat("2026-08-26T02:52:10+00:00")
CASCADE_LAT, CASCADE_LON = 28.255, 85.520  # source zone
WINDOW_PRE_S = 600.0
WINDOW_POST_S = 1500.0
SEGMENT_S = 120.0


def load_window(start: datetime, end: datetime, client: CachedWaveformClient):
    result = client.get_waveforms(
        WaveformRequest(
            EVEREST.site.network,
            EVEREST.site.station,
            EVEREST.site.location,
            EVEREST.site.channel,
            start,
            end,
        )
    )
    if not result.ok:
        return None, None
    trace = result.stream.merge(fill_value="interpolate")[0]
    return np.asarray(trace.data, dtype=float), float(trace.stats.sampling_rate)


def segment_spectra(data: np.ndarray, sr: float, onset_s: float) -> tuple[float, float]:
    proc = preprocess(data, sr)
    start = max(round(onset_s * sr), 0)
    end = min(start + round(SEGMENT_S * sr), proc.size)
    if end - start < int(sr * 5):
        return float("nan"), float("nan")
    return spectral_features(proc[start:end], sr)


def cascade_on_io_evn(client: CachedWaveformClient) -> tuple[float, float]:
    """The cascade's 120 s segment features as seen from IO.EVN."""
    start = CASCADE_ORIGIN - timedelta(seconds=WINDOW_PRE_S)
    end = CASCADE_ORIGIN + timedelta(seconds=WINDOW_POST_S)
    data, sr = load_window(start, end, client)
    if data is None:
        raise SystemExit("cascade window not available on IO.EVN")

    proc = preprocess(data, sr)
    detection = sta_lta(proc, sr, preprocessed=True)
    distance = haversine_km(EVEREST.latitude, EVEREST.longitude, CASCADE_LAT, CASCADE_LON)
    pick = pick_onset(detection.triggers, origin_offset_s=WINDOW_PRE_S, distance_km=distance)
    if not pick.ok:
        raise SystemExit(f"no onset picked for the cascade on IO.EVN: {pick.reason}")
    return segment_spectra(data, sr, pick.onset_s)


def main() -> int:
    if not IO_EVN_CORPUS.exists():
        print(f"No IO.EVN corpus at {IO_EVN_CORPUS}.")
        print("Run: uv run python scripts/harvest_earthquakes.py --station IO.EVN")
        return 1

    client = CachedWaveformClient()
    cascade_lf, cascade_cen = cascade_on_io_evn(client)

    manifest = json.loads(IO_EVN_CORPUS.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for event in manifest["events"]:
        if event["status"] != "ok" or event.get("onset_s") is None:
            continue
        origin = datetime.fromisoformat(event["origin_utc"])
        data, sr = load_window(
            origin - timedelta(seconds=WINDOW_PRE_S),
            origin + timedelta(seconds=WINDOW_POST_S),
            client,
        )
        if data is None:
            continue
        lf, cen = segment_spectra(data, sr, event["onset_s"])
        if not (np.isfinite(lf) and np.isfinite(cen)):
            continue
        rows.append(
            {
                "magnitude": event["magnitude"],
                "distance_km": event["distance_km"],
                "seg_lf": lf,
                "seg_cen": cen,
            }
        )

    if not rows:
        print("No usable IO.EVN earthquakes with recomputable segment features.")
        return 1

    lf = np.array([r["seg_lf"] for r in rows])
    cen = np.array([r["seg_cen"] for r in rows])
    mag = np.array([r["magnitude"] for r in rows])
    dist = np.array([r["distance_km"] for r in rows])

    exceeds_lf = lf >= cascade_lf
    below_cen = cen <= cascade_cen
    joint = exceeds_lf & below_cen

    matched = (mag >= 4.0) & (mag <= 4.6)

    print(f"IO.EVN, 120 s segments (n={len(rows)} earthquakes)")
    print(f"  cascade on IO.EVN:  LF/HF {cascade_lf:.2f}   centroid {cascade_cen:.2f} Hz")
    print(f"  earthquake medians: LF/HF {np.median(lf):.2f}   centroid {np.median(cen):.2f} Hz")
    print()
    print(f"  earthquakes at or above cascade LF/HF:    {exceeds_lf.sum()}/{len(rows)}")
    print(f"  earthquakes at or below cascade centroid: {below_cen.sum()}/{len(rows)}")
    print(
        f"  meeting BOTH (the overlap):               {joint.sum()}/{len(rows)} "
        f"({100 * joint.mean():.1f}%)"
    )
    print(f"  magnitude-matched (M4.0-4.6) meeting both: {joint[matched].sum()}/{matched.sum()}")

    # exp003 found magnitude confounds these features on NK.KKN. Re-check on IO.EVN:
    # if the overlap were just a size effect, that would show here.
    confounds = {
        "lf_vs_magnitude": _rank_corr(lf, mag),
        "centroid_vs_magnitude": _rank_corr(cen, mag),
        "lf_vs_distance": _rank_corr(lf, dist),
        "centroid_vs_distance": _rank_corr(cen, dist),
    }
    print("\n  confounds (rank correlation):")
    for k, v in confounds.items():
        print(f"    {k:<22} {v:+.2f}")

    results = {
        "experiment": "exp010_second_station",
        "station": EVEREST.nslc,
        "segment_s": SEGMENT_S,
        "cascade": {"lf_hf": cascade_lf, "centroid_hz": cascade_cen},
        "earthquakes": {
            "n": len(rows),
            "lf_hf_median": float(np.median(lf)),
            "centroid_median": float(np.median(cen)),
        },
        "overlap": {
            "at_or_above_lf": int(exceeds_lf.sum()),
            "at_or_below_centroid": int(below_cen.sum()),
            "meeting_both": int(joint.sum()),
            "fraction_meeting_both": float(joint.mean()),
            "magnitude_matched_meeting_both": int(joint[matched].sum()),
            "magnitude_matched_n": int(matched.sum()),
        },
        "confounds": confounds,
        "nk_kkn_comparison": {
            "note": "exp005 measured 17.2% overlap on NK.KKN, same 120 s segment basis",
            "overlap_fraction": 0.172,
        },
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {HERE / 'results.json'}")
    print("\nNK.KKN was 17.2% (exp005). Compare, and write FINDINGS.md by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
