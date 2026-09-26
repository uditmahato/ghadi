"""Experiment 018: what false alarm rate does the detector run at on IO.EVN? (issue #3)

**Question.** A false alarm rate is per station (exp007). The only measured rate is
NK.KKN's, 6.8 per station-month (exp009), and it was computed from whole-window
features. IO.EVN, the Everest station 131 km from the 2026 source, has its own site,
noise, and thresholds, and nothing is known about its rate.

**Design.**

* **Corpus.** IO.EVN background noise harvested by ``scripts/harvest_noise.py --station
  IO.EVN`` with the same design as NK.KKN's committed corpus: 2024-01 to 2026-07, months
  the coverage probe found present, 6 hour cells, 3 windows per cell, seed 0, 35 minute
  windows, regional earthquakes and global teleseisms excluded on the shared phase
  window rule.
* **Basis.** The decision-time basis of exp005: for every STA/LTA trigger, the spectral
  features of the 120 s segment after its onset, which is what the detector sees when it
  must decide. A window is a false alarm if any trigger's segment shows a signal and
  meets the station's own mass-movement thresholds.
* **Thresholds, per station.** Each station is held to the 2026 cascade's own segment
  values *at that station*: NK.KKN LF/HF 4.92 and centroid 1.89 Hz (exp005), IO.EVN
  LF/HF 15.07 and centroid 1.53 Hz (exp010). These are fitted to the one positive event,
  so they are the most permissive operating point and the rates are lower bounds.
* **Like with like.** NK.KKN is recomputed on the same segment basis, from its committed
  corpus windows and the local waveform cache, without modifying that corpus. Its
  whole-window rate is reported alongside, for continuity with exp009.
* **Uncertainty.** Exact Poisson 95% interval on each count.

Probability of detection is still not estimable (n = 1), so these rates are half of an
ROC and must not be quoted as detector performance.

    python scripts/harvest_noise.py --station IO.EVN
    GHADI_OFFLINE=1 python experiments/exp018_io_evn_false_alarm_rate/run.py
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import STATION_SITES  # noqa: E402
from ghadi.fdsn import CachedWaveformClient  # noqa: E402

CORPUS = REPO_ROOT / "data" / "corpus"
HOURS_PER_STATION_MONTH = 24 * 30.44

THRESHOLDS = {
    "NK.KKN": {"lf_hf_min": 4.9188, "centroid_hz_max": 1.8852, "source": "exp005 segment"},
    "IO.EVN": {"lf_hf_min": 15.0726, "centroid_hz_max": 1.5325, "source": "exp010 segment"},
}
WHOLE_WINDOW_NK = {"lf_hf_min": 4.141, "centroid_hz_max": 2.041, "source": "exp002 whole window"}


def _harvest_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "harvest_noise", REPO_ROOT / "scripts" / "harvest_noise.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["harvest_noise"] = mod
    spec.loader.exec_module(mod)
    return mod


def poisson_interval(k: int, conf: float = 0.95) -> tuple[float, float]:
    from scipy.stats import chi2

    a = 1 - conf
    lo = 0.0 if k == 0 else float(chi2.ppf(a / 2, 2 * k) / 2)
    hi = float(chi2.ppf(1 - a / 2, 2 * (k + 1)) / 2)
    return lo, hi


def _finite(x: Any) -> bool:
    return isinstance(x, int | float) and math.isfinite(float(x))


def segment_passes(seg: dict[str, Any], thr: dict[str, Any]) -> bool:
    lf, cen = seg.get("spectral_ratio_low_high"), seg.get("spectral_centroid_hz")
    return bool(
        seg.get("signal_present")
        and _finite(lf)
        and _finite(cen)
        and lf >= thr["lf_hf_min"]
        and cen <= thr["centroid_hz_max"]
    )


def whole_passes(features: dict[str, Any], thr: dict[str, Any]) -> bool:
    lf, cen = features.get("spectral_ratio_low_high"), features.get("spectral_centroid_hz")
    return bool(
        _finite(lf) and _finite(cen) and lf >= thr["lf_hf_min"] and cen <= thr["centroid_hz_max"]
    )


def rate_block(n: int, station_months: float) -> dict[str, Any]:
    lo, hi = poisson_interval(n)
    sm = station_months if station_months > 0 else float("nan")
    return {
        "windows": n,
        "per_station_month": round(n / sm, 2),
        "ci95_per_station_month": [round(lo / sm, 2), round(hi / sm, 2)],
    }


def analyse(station: str, rows: list[dict[str, Any]], window_s: float) -> dict[str, Any]:
    thr = THRESHOLDS[station]
    usable = [r for r in rows if r["status"] == "ok"]
    hours = len(usable) * window_s / 3600.0
    sm = hours / HOURS_PER_STATION_MONTH
    triggered = [r for r in usable if r.get("n_triggers", 0) > 0]
    seg_alarms = [
        r for r in triggered if any(segment_passes(s, thr) for s in r.get("trigger_segments", []))
    ]
    statuses: dict[str, int] = {}
    for r in rows:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    rec = {
        "station": station,
        "thresholds": thr,
        "candidate_windows": len(rows),
        "status_counts": statuses,
        "usable_windows": len(usable),
        "hours": round(hours, 1),
        "station_months": round(sm, 3),
        "layers": {
            "sta_lta_trigger": rate_block(len(triggered), sm),
            "segment_spectral_criteria": rate_block(len(seg_alarms), sm),
        },
        "false_alarm_windows": [
            {
                "window_start_utc": r["window_start_utc"],
                "passing_segments": [
                    s for s in r.get("trigger_segments", []) if segment_passes(s, thr)
                ],
            }
            for r in seg_alarms
        ],
        "target_per_station_month": 1.0,
    }
    return rec


def nk_kkn_segment_rows(hn: Any) -> tuple[list[dict[str, Any]], float, dict[str, Any]]:
    """Recompute NK.KKN's committed corpus windows with per-trigger segment features."""
    committed = json.loads((CORPUS / "noise.json").read_text(encoding="utf-8"))
    site = STATION_SITES["NK.KKN"]
    client = CachedWaveformClient()
    rows, mismatched = [], 0
    for r in committed["windows"]:
        if r["status"] != "ok":
            rows.append(r)
            continue
        new = hn.process(datetime.fromisoformat(r["window_start_utc"]), client, site)
        if new["status"] == "ok" and new["features"].get("spectral_ratio_low_high") != r[
            "features"
        ].get("spectral_ratio_low_high"):
            mismatched += 1
        rows.append(new)
    whole = [
        r
        for r in committed["windows"]
        if r["status"] == "ok"
        and r["n_triggers"] > 0
        and whole_passes(r["features"], WHOLE_WINDOW_NK)
    ]
    usable = sum(1 for r in committed["windows"] if r["status"] == "ok")
    sm = usable * committed["window_s"] / 3600.0 / HOURS_PER_STATION_MONTH
    continuity = {
        "basis": "whole window, exp004/exp009 thresholds",
        "thresholds": WHOLE_WINDOW_NK,
        **rate_block(len(whole), sm),
        "recomputed_windows_with_different_whole_window_features": mismatched,
    }
    return rows, committed["window_s"], continuity


def main() -> int:
    hn = _harvest_module()
    results: dict[str, Any] = {"experiment": "exp018_io_evn_false_alarm_rate", "stations": {}}

    evn_path = CORPUS / "noise_IO_EVN.json"
    if not evn_path.exists():
        print("No IO.EVN corpus yet. Run: python scripts/harvest_noise.py --station IO.EVN")
        return 1
    evn = json.loads(evn_path.read_text(encoding="utf-8"))
    results["stations"]["IO.EVN"] = analyse("IO.EVN", evn["windows"], evn["window_s"])
    results["stations"]["IO.EVN"]["corpus"] = {
        k: evn[k] for k in ("created_utc", "period", "stratification", "window_s")
    }

    nk_rows, nk_window_s, continuity = nk_kkn_segment_rows(hn)
    results["stations"]["NK.KKN"] = analyse("NK.KKN", nk_rows, nk_window_s)
    results["stations"]["NK.KKN"]["whole_window_continuity"] = continuity

    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    for st, rec in results["stations"].items():
        seg = rec["layers"]["segment_spectral_criteria"]
        trig = rec["layers"]["sta_lta_trigger"]
        print(
            f"{st}: {rec['usable_windows']} usable windows, {rec['hours']} h = "
            f"{rec['station_months']} station-months; statuses {rec['status_counts']}"
        )
        print(f"   STA/LTA triggers: {trig['windows']} windows, {trig['per_station_month']}/sm")
        print(
            f"   segment criteria: {seg['windows']} windows, {seg['per_station_month']}/sm, "
            f"95% CI {seg['ci95_per_station_month']}"
        )
    c = results["stations"]["NK.KKN"]["whole_window_continuity"]
    mism = c["recomputed_windows_with_different_whole_window_features"]
    print(
        f"NK.KKN whole-window continuity: {c['windows']} windows, {c['per_station_month']}/sm "
        f"(exp009 reported 6.8); recomputed feature mismatches {mism}"
    )
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
