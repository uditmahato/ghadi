"""Experiment 002 — does the M2 feature rework survive contact with real data?

**Question.** Experiment 001 found the temporal features broken: measured against the
global window peak, `emergence_s` reported 307 s for an earthquake and 254 s for noise,
and `duration_ratio` scored highest on diffuse noise. M2 redefined emergence relative to
the trigger onset (issue 2.1), gated the duration features on signal presence (issue
2.3), and added instrument-response deconvolution (issue 2.4).

Do the repaired features order the four exp001 cases correctly on real waveforms?

**Design.** The same four windows as exp001 — the cascade, two real regional
earthquakes, and a quiet-noise control — so the comparison is like for like. Each window
is run through the detector first, and its trigger onset is fed to the feature
extractor, which is the dependency the rework introduced.

Features are computed twice: in raw counts, and in ground velocity after response
deconvolution, to check that issue 2.4 changes the units without changing the ordering.

**What this cannot show.** Four windows, one per class, cannot establish separability at
any false-alarm rate. This experiment checks that the repaired features are *not broken*
in the specific ways exp001 documented. Quantified separation with confidence intervals
is issue 2.6 and needs M1's corpus.

    python experiments/exp002_feature_rework/run.py
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

from ghadi.config import DEFAULT, PRIMARY_STATION  # noqa: E402
from ghadi.detect import sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import extract, preprocess  # noqa: E402

HERE = Path(__file__).parent
EXP001 = REPO_ROOT / "experiments" / "exp001_signal_recon"
WINDOW_PRE_S = 600.0
WINDOW_POST_S = 1500.0
EVENT_UTC = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)


def cases() -> list[dict[str, Any]]:
    """The same four windows as exp001, reusing its committed reference events."""
    out: list[dict[str, Any]] = [
        {"name": "2026-08-26 Bhote Koshi", "label": "mass_movement", "centre": EVENT_UTC},
    ]
    refs = json.loads((EXP001 / "reference_events.json").read_text(encoding="utf-8"))
    for event in refs["events"]:
        centre = datetime.fromisoformat(event["origin_utc"])
        out.append(
            {
                "name": f"Reference EQ M{event['magnitude']:.1f} {centre.date()}",
                "label": "earthquake",
                "centre": centre,
            }
        )
    out.append(
        {
            "name": "Quiet noise (T-7d)",
            "label": "noise",
            "centre": EVENT_UTC - timedelta(days=7),
        }
    )
    return out


def analyse(case: dict[str, Any], client: CachedWaveformClient) -> dict[str, Any]:
    centre = case["centre"]
    start = centre - timedelta(seconds=WINDOW_PRE_S)
    end = centre + timedelta(seconds=WINDOW_POST_S)
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
        return {"case": case["name"], "label": case["label"], "error": result.error}

    stream = result.stream.merge(fill_value="interpolate")
    sr = float(stream[0].stats.sampling_rate)
    counts = np.asarray(stream[0].data, dtype=float)

    # Issue 2.4: the same window in ground velocity, if the response is available.
    inventory = client.get_inventory(PRIMARY_STATION.network, PRIMARY_STATION.station)
    velocity_stream = client.to_velocity(stream, inventory) if inventory is not None else None
    velocity = (
        np.asarray(velocity_stream[0].data, dtype=float) if velocity_stream is not None else None
    )

    row: dict[str, Any] = {"case": case["name"], "label": case["label"]}

    for units, data in (("counts", counts), ("velocity_m_s", velocity)):
        if data is None:
            row[units] = {"error": "instrument response unavailable"}
            continue
        proc = preprocess(data, sr)
        det = sta_lta(proc, sr, preprocessed=True)
        onset = det.first_trigger.on_s if det.first_trigger else None
        feats = extract(proc, sr, preprocessed=True, onset_s=onset)
        row[units] = {
            "onset_s": onset,
            "n_triggers": len(det.triggers),
            "max_sta_lta": det.max_ratio,
            "signal_present": feats.signal_present,
            **feats.as_dict(),
        }
    return row


def main() -> int:
    client = CachedWaveformClient()
    rows = [analyse(c, client) for c in cases()]

    results = {
        "experiment": "exp002_feature_rework",
        "run_utc": datetime.now(UTC).isoformat(),
        "station": PRIMARY_STATION.nslc,
        "config": {
            "band_hz": list(DEFAULT.seismic.band_hz),
            "sta_s": DEFAULT.seismic.sta_s,
            "lta_s": DEFAULT.seismic.lta_s,
            "taper_s": DEFAULT.seismic.taper_s,
            "trigger_on": DEFAULT.seismic.trigger_on,
            "spectral_split_hz": DEFAULT.seismic.spectral_split_hz,
            "signal_presence_ratio": DEFAULT.seismic.signal_presence_ratio,
        },
        "cases": rows,
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    def show(units: str) -> None:
        print(f"\n=== {units} ===")
        header = (
            f"{'case':<32} {'sig?':>5} {'onset_s':>8} {'emerg_s':>8} "
            f"{'dur_ratio':>10} {'LF/HF':>8} {'centroid':>9} {'BROKEN_emerg':>13}"
        )
        print(header)
        for row in rows:
            if "error" in row or "error" in row.get(units, {}):
                print(f"{row['case']:<32}  {row.get(units, {}).get('error', row.get('error'))}")
                continue
            f = row[units]

            def fmt(value: Any, width: int, places: int = 2) -> str:
                if value is None:
                    return f"{'-':>{width}}"
                if isinstance(value, float) and np.isnan(value):
                    return f"{'NaN':>{width}}"
                return f"{value:>{width}.{places}f}"

            print(
                f"{row['case']:<32} {f['signal_present']!s:>5} "
                f"{fmt(f['onset_s'], 8, 1)} {fmt(f['emergence_s'], 8, 1)} "
                f"{fmt(f['duration_ratio'], 10, 3)} {fmt(f['spectral_ratio_low_high'], 8)} "
                f"{fmt(f['spectral_centroid_hz'], 9)} "
                f"{fmt(f['emergence_s_global_peak'], 13, 1)}"
            )

    show("counts")
    show("velocity_m_s")
    print(f"\nWrote {HERE / 'results.json'}")
    print("\nUpdate FINDINGS.md by hand. Negative results are committed, not deleted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
