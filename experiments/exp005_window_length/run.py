"""Experiment 005 — is the separation an artefact of window length?

**The worry.** Every feature so far is computed over a fixed 2100 s window. The cascade
fills such a window: its energy persists for more than 25 minutes. A regional earthquake
does not — it occupies two or three minutes, and the remaining ~90% of the window is
background noise.

So the whole-window spectra of an earthquake are a *mixture* of the earthquake and the
background, while the cascade's are mostly the cascade. If NK.KKN's background noise is
higher-frequency than an earthquake, that mixture drags earthquakes toward high
frequency and **manufactures separation that the sources themselves do not have**. The
exp003 overlap figures would then be optimistic for the wrong reason.

**Test.** Recompute both classes over a bounded segment starting at the picked onset, so
each event is characterised by its own arrival rather than by how much of the window it
happens to occupy. Compare the overlap to exp003's whole-window result.

Reads only cached waveforms — no new network requests.

    python experiments/exp005_window_length/run.py --segment-s 120
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import PRIMARY_STATION  # noqa: E402
from ghadi.detect import sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import extract, preprocess, spectral_features  # noqa: E402

HERE = Path(__file__).parent
EARTHQUAKES = REPO_ROOT / "data" / "corpus" / "earthquakes.json"
CASCADE_ORIGIN = datetime.fromisoformat("2026-08-26T02:52:10+00:00")
WINDOW_PRE_S = 600.0
WINDOW_POST_S = 1500.0


def load_window(start: datetime, end: datetime, client: CachedWaveformClient):
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
        return None, None
    trace = result.stream.merge(fill_value="interpolate")[0]
    return np.asarray(trace.data, dtype=float), float(trace.stats.sampling_rate)


def segment_spectra(
    data: np.ndarray, sr: float, onset_s: float, segment_s: float
) -> tuple[float, float]:
    """Spectral features over ``segment_s`` starting at the onset."""
    proc = preprocess(data, sr)
    start = max(round(onset_s * sr), 0)
    end = min(start + round(segment_s * sr), proc.size)
    if end - start < int(sr * 5):
        return float("nan"), float("nan")
    return spectral_features(proc[start:end], sr)


def background_spectra(data: np.ndarray, sr: float, seconds: float = 400.0) -> tuple[float, float]:
    """Spectral features of the pre-event background, for reference."""
    proc = preprocess(data, sr)
    end = min(round(seconds * sr), proc.size)
    if end < int(sr * 5):
        return float("nan"), float("nan")
    return spectral_features(proc[:end], sr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment-s", type=float, default=120.0)
    args = parser.parse_args(argv)

    client = CachedWaveformClient()

    # --- the cascade ---------------------------------------------------------------
    start = CASCADE_ORIGIN - timedelta(seconds=WINDOW_PRE_S)
    end = CASCADE_ORIGIN + timedelta(seconds=WINDOW_POST_S)
    data, sr = load_window(start, end, client)
    if data is None:
        print("Cascade window not cached; run exp002 first.")
        return 1

    proc = preprocess(data, sr)
    detection = sta_lta(proc, sr, preprocessed=True)
    cascade_onset = detection.first_trigger.on_s if detection.first_trigger else 610.0
    cascade_whole = extract(proc, sr, preprocessed=True, onset_s=cascade_onset)
    cascade_lf, cascade_cen = segment_spectra(data, sr, cascade_onset, args.segment_s)
    bg_lf, bg_cen = background_spectra(data, sr)

    print(f"Segment length: {args.segment_s:.0f} s, from the picked onset\n")
    print("Cascade:")
    print(
        f"  whole window  LF/HF {cascade_whole.spectral_ratio_low_high:6.2f}   "
        f"centroid {cascade_whole.spectral_centroid_hz:5.2f} Hz"
    )
    print(f"  segment       LF/HF {cascade_lf:6.2f}   centroid {cascade_cen:5.2f} Hz")
    print(f"  pre-event bg  LF/HF {bg_lf:6.2f}   centroid {bg_cen:5.2f} Hz")

    # --- earthquakes ---------------------------------------------------------------
    manifest = json.loads(EARTHQUAKES.read_text(encoding="utf-8"))
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
        lf, cen = segment_spectra(data, sr, event["onset_s"], args.segment_s)
        if not (np.isfinite(lf) and np.isfinite(cen)):
            continue
        rows.append(
            {
                "magnitude": event["magnitude"],
                "distance_km": event["distance_km"],
                "whole_lf": event["features"]["spectral_ratio_low_high"],
                "whole_cen": event["features"]["spectral_centroid_hz"],
                "seg_lf": lf,
                "seg_cen": cen,
            }
        )

    if not rows:
        print("\nNo cached earthquake windows found.")
        return 1

    whole_lf = np.array([r["whole_lf"] for r in rows])
    whole_cen = np.array([r["whole_cen"] for r in rows])
    seg_lf = np.array([r["seg_lf"] for r in rows])
    seg_cen = np.array([r["seg_cen"] for r in rows])

    whole_joint = (whole_lf >= cascade_whole.spectral_ratio_low_high) & (
        whole_cen <= cascade_whole.spectral_centroid_hz
    )
    seg_joint = (seg_lf >= cascade_lf) & (seg_cen <= cascade_cen)

    print(f"\nEarthquakes re-measured on the same segment length (n={len(rows)}):")
    print(
        f"  whole window  LF/HF median {np.median(whole_lf):5.2f}   "
        f"centroid median {np.median(whole_cen):5.2f} Hz"
    )
    print(
        f"  segment       LF/HF median {np.median(seg_lf):5.2f}   "
        f"centroid median {np.median(seg_cen):5.2f} Hz"
    )

    print("\nOverlap with the cascade (both criteria, each measured like-for-like):")
    print(f"  whole window  {whole_joint.sum():>3}/{len(rows)}  ({100 * whole_joint.mean():.1f}%)")
    print(f"  segment       {seg_joint.sum():>3}/{len(rows)}  ({100 * seg_joint.mean():.1f}%)")

    results = {
        "experiment": "exp005_window_length",
        "segment_s": args.segment_s,
        "cascade": {
            "whole_lf_hf": cascade_whole.spectral_ratio_low_high,
            "whole_centroid_hz": cascade_whole.spectral_centroid_hz,
            "segment_lf_hf": cascade_lf,
            "segment_centroid_hz": cascade_cen,
            "background_lf_hf": bg_lf,
            "background_centroid_hz": bg_cen,
            "onset_s": cascade_onset,
        },
        "earthquakes": {
            "n": len(rows),
            "whole_lf_hf_median": float(np.median(whole_lf)),
            "whole_centroid_median": float(np.median(whole_cen)),
            "segment_lf_hf_median": float(np.median(seg_lf)),
            "segment_centroid_median": float(np.median(seg_cen)),
        },
        "overlap": {
            "whole_window": int(whole_joint.sum()),
            "segment": int(seg_joint.sum()),
            "n": len(rows),
        },
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {HERE / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
