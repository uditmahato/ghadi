"""Experiment 006 — how much does teleseism suppression buy?

**Question.** exp004 measured 12.9 false alarms per station-month and found that two of
the four survivors were distant earthquakes: an M6.2 in the Bonin Islands with an M5.5
in Kamchatka in one window, an M6.0 in Indonesia in another. Those were identified by
hand, on four windows. This applies the suppression rule systematically — every trigger
in every noise window, against a global M>=5.5 catalogue — and asks what the corrected
rate is.

**Method.** Triggers are recomputed from the cached waveforms rather than read from the
noise manifest, because the manifest stores trigger *counts* and suppression needs
trigger *times*. A trigger is suppressed when a catalogued global origin predicts a P
arrival within tolerance of it (``ghadi.teleseism``).

**The failure mode this must not have.** Over-suppression would hide real local events,
which is far worse than a false alarm. Two guards: a magnitude floor, below which a
teleseism cannot trip a regional station, and a tolerance window narrow relative to the
interval between large global earthquakes. This experiment reports how much of the
*noise* corpus is suppressed, which bounds how aggressive the rule is.

Reads only cached waveforms and the cached catalogue — no network.

    python experiments/exp006_teleseism_suppression/run.py
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

from ghadi.config import PRIMARY_STATION  # noqa: E402
from ghadi.detect import sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import preprocess  # noqa: E402
from ghadi.teleseism import Origin, explain  # noqa: E402

HERE = Path(__file__).parent
NOISE = REPO_ROOT / "data" / "corpus" / "noise.json"
CATALOGUE = REPO_ROOT / "data" / "corpus" / "global_catalogue.json"

STATION_LAT, STATION_LON = 27.800, 85.279
CASCADE_LF_HF = 4.141
CASCADE_CENTROID_HZ = 2.041
HOURS_PER_STATION_MONTH = 24 * 30.44


def load_origins() -> list[Origin]:
    data = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    return [
        Origin(
            time_utc=datetime.fromisoformat(o["time_utc"]),
            latitude=o["latitude"],
            longitude=o["longitude"],
            magnitude=o["magnitude"],
            event_id=o.get("event_id", ""),
            place=o.get("place", ""),
        )
        for o in data["origins"]
    ]


def passes_spectral(features: dict[str, Any]) -> bool:
    lf = features.get("spectral_ratio_low_high")
    centroid = features.get("spectral_centroid_hz")
    if lf is None or centroid is None or not (np.isfinite(lf) and np.isfinite(centroid)):
        return False
    return bool(lf >= CASCADE_LF_HF and centroid <= CASCADE_CENTROID_HZ)


def main() -> int:
    noise = json.loads(NOISE.read_text(encoding="utf-8"))
    usable = [w for w in noise["windows"] if w["status"] == "ok"]
    origins = load_origins()
    window_s = float(noise["window_s"])
    station_months = len(usable) * window_s / 3600.0 / HOURS_PER_STATION_MONTH

    client = CachedWaveformClient()
    rows: list[dict[str, Any]] = []

    for window in usable:
        if window["n_triggers"] == 0:
            continue
        start = datetime.fromisoformat(window["window_start_utc"])
        end = datetime.fromisoformat(window["window_end_utc"])
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
            continue
        trace = result.stream.merge(fill_value="interpolate")[0]
        sr = float(trace.stats.sampling_rate)
        proc = preprocess(np.asarray(trace.data, dtype=float), sr)
        detection = sta_lta(proc, sr, preprocessed=True)

        suppressed_any = False
        reasons: list[str] = []
        for trigger in detection.triggers:
            verdict = explain(
                start + timedelta(seconds=trigger.on_s), origins, STATION_LAT, STATION_LON
            )
            if verdict.suppressed:
                suppressed_any = True
                reasons.append(verdict.reason)

        rows.append(
            {
                "window_start_utc": window["window_start_utc"],
                "n_triggers": len(detection.triggers),
                "spectral_pass": passes_spectral(window["features"]),
                "suppressed": suppressed_any,
                "reasons": reasons[:2],
                "lf_hf": window["features"]["spectral_ratio_low_high"],
                "centroid_hz": window["features"]["spectral_centroid_hz"],
            }
        )

    triggering = len(rows)
    suppressed = sum(1 for r in rows if r["suppressed"])
    fa_before = [r for r in rows if r["spectral_pass"]]
    fa_after = [r for r in fa_before if not r["suppressed"]]

    def rate(n: int) -> float:
        return n / station_months if station_months else float("nan")

    print(f"Noise corpus: {len(usable)} usable windows = {station_months:.2f} station-months")
    print(f"Global catalogue: {len(origins)} origins at M>=5.5\n")
    print(f"{'quantity':<44} {'count':>7} {'per station-month':>19}")
    print(
        f"{'triggering windows (STA/LTA baseline)':<44} {triggering:>7} {rate(triggering):>19.1f}"
    )
    print(f"{'  of which explained by a teleseism':<44} {suppressed:>7} {rate(suppressed):>19.1f}")
    print(
        f"{'passing spectral criteria (exp004)':<44} {len(fa_before):>7} "
        f"{rate(len(fa_before)):>19.1f}"
    )
    print(f"{'  after teleseism suppression':<44} {len(fa_after):>7} {rate(len(fa_after)):>19.1f}")

    print("\nFalse alarms before suppression:")
    for r in fa_before:
        mark = "SUPPRESSED" if r["suppressed"] else "survives  "
        print(
            f"  {mark}  {r['window_start_utc'][:16]}  LF/HF {r['lf_hf']:6.2f}  "
            f"cen {r['centroid_hz']:.2f}"
        )
        for reason in r["reasons"]:
            print(f"              {reason}")

    over_suppression = suppressed / triggering if triggering else float("nan")
    print(
        f"\nOver-suppression check: {suppressed}/{triggering} "
        f"({100 * over_suppression:.1f}%) of all triggering noise windows are attributed\n"
        "  to a distant earthquake. A rule that explained most of them would be too\n"
        "  aggressive to trust near a real event."
    )

    results = {
        "experiment": "exp006_teleseism_suppression",
        "station_months": station_months,
        "catalogue_origins": len(origins),
        "triggering_windows": triggering,
        "suppressed_windows": suppressed,
        "false_alarms_before": len(fa_before),
        "false_alarms_after": len(fa_after),
        "rate_before_per_station_month": rate(len(fa_before)),
        "rate_after_per_station_month": rate(len(fa_after)),
        "over_suppression_fraction": over_suppression,
        "windows": rows,
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {HERE / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
