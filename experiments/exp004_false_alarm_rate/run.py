"""Experiment 004 — what false-alarm rate does the detector actually run at?

**Question.** Everything so far has been about whether the cascade *looks* different.
That is only half a detector. The other half is how often something that is not a mass
movement gets through, and until now there has been no denominator: "it fired on the
cascade" is an anecdote without one. The handoff's target is **≤ 1 false alarm per
station-month** (M3 exit criteria, issue 5.3).

**What is measured.** Three layers, each a subset of the one above:

1. **STA/LTA alone** — the honest baseline every learned model must beat (issue 3.1).
   How many noise windows produce at least one trigger?
2. **STA/LTA + signal presence** — the gate from issue 2.3.
3. **STA/LTA + signal presence + the spectral criteria** — the detector as currently
   constituted, using the cascade's own feature values as thresholds.

Earthquake-driven false alarms are counted separately from the earthquake corpus,
because they arrive at a different rate and are a different problem: an earthquake is a
real event misclassified, not a quiet period misread.

**What cannot be measured, and the honest statement of it.** There is exactly one
positive example. **Probability of detection is not estimable from n = 1** — any figure
would be 100% by construction, since the thresholds are that event's own values. This
experiment therefore reports a false-alarm rate against an *unknown* detection rate,
which is half of an ROC and must never be quoted as if it were the whole one.

    python experiments/exp004_false_alarm_rate/run.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

HERE = Path(__file__).parent
NOISE = REPO_ROOT / "data" / "corpus" / "noise.json"
EARTHQUAKES = REPO_ROOT / "data" / "corpus" / "earthquakes.json"

# The 26 August 2026 cascade on this pipeline (exp002). Used as thresholds, which is
# the most permissive possible choice: they are fitted to the one event we detect.
CASCADE_LF_HF = 4.141
CASCADE_CENTROID_HZ = 2.041

HOURS_PER_STATION_MONTH = 24 * 30.44


def passes_spectral(features: dict[str, Any]) -> bool:
    lf = features.get("spectral_ratio_low_high")
    centroid = features.get("spectral_centroid_hz")
    if lf is None or centroid is None:
        return False
    if not (np.isfinite(lf) and np.isfinite(centroid)):
        return False
    return bool(lf >= CASCADE_LF_HF and centroid <= CASCADE_CENTROID_HZ)


def main() -> int:
    if not NOISE.exists():
        print(f"No noise corpus at {NOISE}. Run scripts/harvest_noise.py first.")
        return 1

    noise = json.loads(NOISE.read_text(encoding="utf-8"))
    usable = [w for w in noise["windows"] if w["status"] == "ok"]
    if not usable:
        print("Noise corpus has no usable windows.")
        return 1

    window_s = float(noise["window_s"])
    total_hours = len(usable) * window_s / 3600.0
    station_months = total_hours / HOURS_PER_STATION_MONTH

    triggered = [w for w in usable if w["n_triggers"] > 0]
    gated = [w for w in triggered if w.get("signal_present")]
    spectral = [w for w in gated if passes_spectral(w["features"])]

    def rate(n: int) -> float:
        return n / station_months if station_months > 0 else float("nan")

    layers = [
        ("STA/LTA alone (baseline)", len(triggered)),
        ("+ signal-presence gate", len(gated)),
        ("+ spectral criteria", len(spectral)),
    ]

    print(f"Noise corpus: {len(usable)} usable windows of {window_s / 60:.0f} min")
    print(f"  {total_hours:.1f} hours = {station_months:.2f} station-months\n")
    print(f"{'layer':<32} {'windows':>8} {'per station-month':>19}")
    for name, count in layers:
        print(f"{name:<32} {count:>8} {rate(count):>19.1f}")

    # Earthquakes are a separate false-alarm population with its own arrival rate.
    eq_block: dict[str, Any] = {}
    if EARTHQUAKES.exists():
        eq = json.loads(EARTHQUAKES.read_text(encoding="utf-8"))
        eq_ok = [e for e in eq["events"] if e["status"] == "ok"]
        eq_pass = [e for e in eq_ok if passes_spectral(e["features"])]
        eq_block = {
            "usable": len(eq_ok),
            "passing_spectral": len(eq_pass),
            "fraction": len(eq_pass) / len(eq_ok) if eq_ok else float("nan"),
        }
        print(
            f"\nEarthquakes passing the same spectral criteria: "
            f"{len(eq_pass)}/{len(eq_ok)} ({100 * eq_block['fraction']:.1f}%)"
        )
        print(
            "  These arrive at the regional earthquake rate, not the noise rate, and\n"
            "  are a different failure: a real event misclassified, not a quiet\n"
            "  period misread. See exp003 for the magnitude and distance breakdown."
        )

    results = {
        "experiment": "exp004_false_alarm_rate",
        "noise_corpus": {
            "usable_windows": len(usable),
            "window_s": window_s,
            "total_hours": total_hours,
            "station_months": station_months,
        },
        "thresholds": {
            "source": "the 26 Aug 2026 cascade's own values (exp002)",
            "lf_hf_min": CASCADE_LF_HF,
            "centroid_hz_max": CASCADE_CENTROID_HZ,
            "caveat": (
                "fitted to the single positive event, so this is the most permissive "
                "operating point available and the rates below are lower bounds"
            ),
        },
        "layers": [
            {"name": name, "windows": count, "per_station_month": rate(count)}
            for name, count in layers
        ],
        "earthquakes": eq_block,
        "probability_of_detection": {
            "estimable": False,
            "reason": (
                "n = 1 positive example, and the thresholds are that example's own "
                "feature values, so any POD figure would be 100% by construction"
            ),
        },
        "target": {"false_alarms_per_station_month": 1.0, "source": "HANDOFF M3/issue 5.3"},
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\nTarget: <= 1 false alarm per station-month (handoff M3)")
    final = rate(len(spectral))
    verdict = "within" if final <= 1.0 else "above"
    print(f"Detector as constituted: {final:.1f} per station-month — {verdict} target.")
    print(
        "\nThis is half an ROC. Probability of detection is NOT estimable: there is one\n"
        "positive example and the thresholds are its own values, so any POD figure\n"
        "would be 100% by construction. Do not quote this rate as detector performance."
    )
    print(f"\nWrote {HERE / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
