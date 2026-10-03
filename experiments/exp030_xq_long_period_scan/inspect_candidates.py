"""Experiment 030, second step: what do the unexplained candidates look like up close?

The scan (``run.py``) leaves a list of long period events that no catalogued earthquake
explains. A long period ratio cannot say what they are. This fetches the short period
record around each one at its two strongest stations and runs the project's own
detector and classifier on it, so each candidate is sorted into one of:

* **no short period arrival**: nothing triggers near the long period peak. A long
  period transient with no body of short period energy is an instrument or tilt event,
  or the tail of something distant.
* **earthquake like**: a trigger whose decision segment fails the mass movement rule.
* **mass movement like at one station**, or **at both**.

The thresholds are NK.KKN's, at the default 20 percent margin. They were never set for
these stations, so "like" here means "worth a person's time", nothing more.

    python experiments/exp030_xq_long_period_scan/inspect_candidates.py
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

from ghadi.classify import classify_segment  # noqa: E402
from ghadi.config import DEFAULT  # noqa: E402
from ghadi.detect import sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import extract, preprocess  # noqa: E402
from ghadi.features_3c import hv_ratio  # noqa: E402

HERE = Path(__file__).resolve().parent
BEFORE_S, AFTER_S = 600.0, 600.0
SEARCH = (-360.0, 90.0)  # where a short period onset may sit relative to the long period peak
N_DISTANT = 30


def load(
    client: CachedWaveformClient, code: str, channel: str, start: datetime, end: datetime
) -> tuple[np.ndarray | None, float]:
    r = client.get_waveforms(WaveformRequest("XQ", code, "", channel, start, end))
    if not r.ok:
        return None, 0.0
    tr = r.stream.merge(fill_value="interpolate")[0]
    if tr.stats.npts < tr.stats.sampling_rate * 600:
        return None, 0.0
    return np.asarray(tr.data, dtype=float), float(tr.stats.sampling_rate)


def look(client: CachedWaveformClient, code: str, peak: datetime) -> dict[str, Any]:
    start, end = peak - timedelta(seconds=BEFORE_S), peak + timedelta(seconds=AFTER_S)
    z, sr = load(client, code, "HHZ", start, end)
    if z is None:
        return {"station": code, "status": "no_short_period_data"}
    proc = preprocess(z, sr)
    det = sta_lta(proc, sr, preprocessed=True)
    near = [t for t in det.triggers if SEARCH[0] <= t.on_s - BEFORE_S <= SEARCH[1]]
    rec: dict[str, Any] = {
        "station": code,
        "status": "ok",
        "triggers_in_window": len(det.triggers),
        "max_sta_lta": round(det.max_ratio, 1),
    }
    if not near:
        rec["verdict"] = "no_short_period_arrival"
        return rec
    trig = max(near, key=lambda t: t.peak_ratio)
    try:
        seg = extract(
            proc,
            sr,
            preprocessed=True,
            onset_s=trig.on_s,
            segment_s=DEFAULT.seismic.decision_segment_s,
        )
    except ValueError:
        rec["verdict"] = "segment_too_short"
        return rec
    hv = None
    n, _ = load(client, code, "HH1", start, end)
    e, _ = load(client, code, "HH2", start, end)
    if n is not None and e is not None:
        m = min(proc.size, n.size, e.size)
        a = max(round(trig.on_s * sr), 0)
        b = min(a + round(DEFAULT.seismic.decision_segment_s * sr), m)
        if b - a > 2:
            v = hv_ratio(proc[a:b], preprocess(n[:m], sr)[a:b], preprocess(e[:m], sr)[a:b])
            hv = float(v) if np.isfinite(v) else None
    cls = classify_segment(seg.spectral_ratio_low_high, seg.spectral_centroid_hz, segment_hv=hv)
    rec.update(
        {
            "onset_s_from_peak": round(trig.on_s - BEFORE_S, 1),
            "peak_sta_lta": round(trig.peak_ratio, 1),
            "lf_hf": round(float(seg.spectral_ratio_low_high), 2),
            "centroid_hz": round(float(seg.spectral_centroid_hz), 2),
            "duration_80_s": round(float(seg.duration_80_s), 1),
            "hv_segment": None if hv is None else round(hv, 2),
            "signal_present": bool(seg.signal_present),
            "verdict": "mass_movement_like" if cls.mass_movement_like else "earthquake_like",
        }
    )
    return rec


def main() -> int:
    scan = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    client = CachedWaveformClient()
    todo = [("local", r) for r in scan["local_candidates"]]
    todo += [("distant_like", r) for r in scan["unexplained_distant_like"][:N_DISTANT]]
    out: list[dict[str, Any]] = []
    for kind, r in todo:
        peak = datetime.fromisoformat(r["peak_utc"]).astimezone(UTC)
        stations = list(r["ratios"])[:2]
        looks = [look(client, code, peak) for code in stations]
        verdicts = [x.get("verdict") for x in looks if x["status"] == "ok"]
        likes = verdicts.count("mass_movement_like")
        if not verdicts:
            summary = "no_short_period_data"
        elif likes == 2:
            summary = "mass_movement_like_at_both"
        elif likes == 1:
            summary = "mass_movement_like_at_one"
        elif "earthquake_like" in verdicts:
            summary = "earthquake_like"
        else:
            summary = "no_short_period_arrival"
        out.append(
            {
                "kind": kind,
                "peak_utc": r["peak_utc"],
                "duration_s": r["duration_s"],
                "strongest_station": r["strongest_station"],
                "strongest_ratio": r["strongest_ratio"],
                "contrast": r["contrast"],
                "summary": summary,
                "stations": looks,
            }
        )
        print(f"   {r['peak_utc'][:19]} {kind:<12} {summary}", flush=True)
    counts: dict[str, dict[str, int]] = {}
    for row in out:
        counts.setdefault(row["kind"], {})
        counts[row["kind"]][row["summary"]] = counts[row["kind"]].get(row["summary"], 0) + 1
    result = {
        "experiment": "exp030_xq_long_period_scan",
        "step": "inspect",
        "counts": counts,
        "candidates": out,
    }
    (HERE / "inspection.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(counts, indent=1))
    for row in out:
        if row["summary"].startswith("mass_movement_like"):
            print(row["peak_utc"][:19], row["kind"], row["summary"], "contrast", row["contrast"])
            for s in row["stations"]:
                print(
                    "     ",
                    {
                        k: s.get(k)
                        for k in (
                            "station",
                            "verdict",
                            "onset_s_from_peak",
                            "lf_hf",
                            "centroid_hz",
                            "hv_segment",
                            "duration_80_s",
                            "peak_sta_lta",
                        )
                    },
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
