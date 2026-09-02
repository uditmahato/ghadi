"""Experiment 003 — does the spectral separation survive a real earthquake corpus?

**Question.** exp001 and exp002 compared the 26 August 2026 cascade against *two*
hand-picked earthquakes, and the two spectral features separated cleanly. Both
experiments said in terms that four windows cannot establish separability. Issue 1.2
has now harvested a real corpus. Does the separation hold at n=64?

**Method.** Take every usable earthquake in ``data/corpus/earthquakes.json``, and ask
where the cascade sits in that population. Because a threshold placed exactly at the
cascade's own value is the most permissive choice available — it is fitted to the one
event we are trying to detect — the fraction of earthquakes meeting it is a *lower
bound* on the false-alarm rate any real operating point would incur.

Confounds are checked rather than assumed: magnitude and epicentral distance both
plausibly drive spectral content, and the corpus is compared to the cascade under
magnitude matching and distance matching as well as in the raw.

    python experiments/exp003_corpus_separation/run.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

HERE = Path(__file__).parent
MANIFEST = REPO_ROOT / "data" / "corpus" / "earthquakes.json"

# The 26 August 2026 cascade, as measured in exp002 on the same pipeline.
CASCADE_LF_HF = 4.141
CASCADE_CENTROID_HZ = 2.041
CASCADE_DISTANCE_KM = 55.9
# USGS initially catalogued the cascade's signal as M4.4 before identifying it as
# landslide-generated, which is the only size figure available for it.
CASCADE_EQUIVALENT_M = 4.4


def rank_correlation(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = manifest["events"]
    ok = [r for r in rows if r["status"] == "ok"]

    lf = np.array([r["features"]["spectral_ratio_low_high"] for r in ok])
    centroid = np.array([r["features"]["spectral_centroid_hz"] for r in ok])
    distance = np.array([r["distance_km"] for r in ok])
    magnitude = np.array([r["magnitude"] for r in ok])

    exceeds_lf = lf >= CASCADE_LF_HF
    below_centroid = centroid <= CASCADE_CENTROID_HZ
    joint = exceeds_lf & below_centroid

    # Availability: which candidates had no waveform, and when.
    missing = [r for r in rows if r["status"] == "no_waveform"]
    missing_by_date = Counter(r["origin_utc"][:10] for r in missing)

    magnitude_matched = (magnitude >= 4.0) & (magnitude <= 4.6)
    near_and_matched = magnitude_matched & (distance < 250)

    results: dict[str, Any] = {
        "experiment": "exp003_corpus_separation",
        "corpus": {
            "candidates": len(rows),
            "usable": len(ok),
            "missing_waveform": len(missing),
            "missing_top_dates": missing_by_date.most_common(5),
            "windows_with_pre_origin_triggers": sum(
                1 for r in rows if r.get("n_rejected_before_origin", 0) > 0
            ),
            "pre_origin_triggers_rejected": sum(r.get("n_rejected_before_origin", 0) for r in rows),
        },
        "cascade": {
            "lf_hf": CASCADE_LF_HF,
            "centroid_hz": CASCADE_CENTROID_HZ,
            "distance_km": CASCADE_DISTANCE_KM,
        },
        "earthquake_population": {
            "n": len(ok),
            "lf_hf": {
                "median": float(np.median(lf)),
                "p10": float(np.percentile(lf, 10)),
                "p90": float(np.percentile(lf, 90)),
                "max": float(lf.max()),
            },
            "centroid_hz": {
                "median": float(np.median(centroid)),
                "p10": float(np.percentile(centroid, 10)),
                "p90": float(np.percentile(centroid, 90)),
                "min": float(centroid.min()),
            },
        },
        "overlap": {
            "eq_at_or_above_cascade_lf_hf": int(exceeds_lf.sum()),
            "eq_at_or_below_cascade_centroid": int(below_centroid.sum()),
            "eq_meeting_both": int(joint.sum()),
            "fraction_meeting_both": float(joint.mean()),
        },
        "confounds": {
            "lf_hf_vs_distance_rank_r": rank_correlation(lf, distance),
            "centroid_vs_distance_rank_r": rank_correlation(centroid, distance),
            "lf_hf_vs_magnitude_rank_r": rank_correlation(lf, magnitude),
            "centroid_vs_magnitude_rank_r": rank_correlation(centroid, magnitude),
        },
        "matched_comparisons": {
            "magnitude_matched": {
                "criterion": "M 4.0-4.6",
                "n": int(magnitude_matched.sum()),
                "meeting_both": int(joint[magnitude_matched].sum()),
            },
            "magnitude_and_distance_matched": {
                "criterion": "M 4.0-4.6 and < 250 km",
                "n": int(near_and_matched.sum()),
                "meeting_both": int(joint[near_and_matched].sum()),
            },
        },
    }

    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"Corpus: {len(rows)} candidates, {len(ok)} usable, {len(missing)} missing waveform")
    print(f"  missing clusters on: {missing_by_date.most_common(3)}")
    print(
        f"  pre-origin triggers rejected: {results['corpus']['pre_origin_triggers_rejected']} "
        f"across {results['corpus']['windows_with_pre_origin_triggers']} windows"
    )

    print(f"\nEarthquake population (n={len(ok)}):")
    print(
        f"  LF/HF     median {np.median(lf):.2f}  p10 {np.percentile(lf, 10):.2f}  "
        f"p90 {np.percentile(lf, 90):.2f}  max {lf.max():.2f}"
    )
    print(
        f"  centroid  median {np.median(centroid):.2f}  p10 {np.percentile(centroid, 10):.2f}  "
        f"p90 {np.percentile(centroid, 90):.2f}  min {centroid.min():.2f}"
    )
    print(f"\nCascade: LF/HF {CASCADE_LF_HF}, centroid {CASCADE_CENTROID_HZ} Hz")
    print(
        f"  earthquakes at or above cascade LF/HF:    {exceeds_lf.sum()}/{len(ok)} "
        f"({100 * exceeds_lf.mean():.0f}%)"
    )
    print(
        f"  earthquakes at or below cascade centroid: {below_centroid.sum()}/{len(ok)} "
        f"({100 * below_centroid.mean():.0f}%)"
    )
    print(
        f"  earthquakes meeting BOTH:                 {joint.sum()}/{len(ok)} "
        f"({100 * joint.mean():.1f}%)"
    )

    print("\nConfounds (rank correlation):")
    for key, value in results["confounds"].items():
        print(f"  {key:<34} {value:+.2f}")

    print("\nMatched comparisons (both criteria):")
    for name, block in results["matched_comparisons"].items():
        print(f"  {name:<32} {block['meeting_both']}/{block['n']}  [{block['criterion']}]")

    print(f"\nWrote {HERE / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
