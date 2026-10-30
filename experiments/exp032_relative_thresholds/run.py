"""Experiment 032: do thresholds set from each station's own earthquakes carry over?

exp031 found that the 2017 Bondo rock avalanche sits in the low frequency tail of its
own region's earthquakes at every Swiss station, but the Nepal thresholds, which are
absolute values from one event on two stations, pass it at only one station of five.
That suggests a rule stated relative to each station's own earthquakes: a segment is
mass movement like when its LF/HF is above a high quantile of that station's earthquake
LF/HF and its centroid is below the matching low quantile of their centroids.

This measures, for a sweep of quantiles, on seven station records of two events:

* how many of the seven the relative rule passes (the 2026 event on NK.KKN and IO.EVN,
  Bondo on five Swiss stations),
* what share of each station's earthquakes it passes, each earthquake judged against
  quantiles computed without it,
* and for the two Nepal stations, the false alarm rate on the noise corpora at the
  spectral layer (exp018's basis), against the current absolute rule on the same rows.

The quantile is a choice made after seeing Bondo, so the result is a sweep, not a tuned
operating point. Everything is offline: the Nepal corpora and the Swiss results come
from the cache and from exp031.

    python experiments/exp032_relative_thresholds/run.py
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import DEFAULT, STATION_SITES  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import preprocess, spectral_features  # noqa: E402

HERE = Path(__file__).resolve().parent
CORPUS = REPO_ROOT / "data" / "corpus"
EXP031 = REPO_ROOT / "experiments" / "exp031_bondo_outside_event" / "results.json"
HOURS_PER_STATION_MONTH = 24 * 30.44

QUANTILES = (0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
SEGMENT_S = DEFAULT.seismic.decision_segment_s
WINDOW_PRE_S, WINDOW_POST_S = 600.0, 1500.0

# The 2026 event's segment values on each Nepal station (exp005, exp010).
CASCADE = {
    "NK.KKN": (4.918825432527951, 1.8851624520050314),
    "IO.EVN": (15.072605742437103, 1.5325246132329207),
}
CORPUS_FILE = {"NK.KKN": "earthquakes.json", "IO.EVN": "earthquakes_IO_EVN.json"}
NOISE_FILE = {"NK.KKN": "noise.json", "IO.EVN": "noise_IO_EVN.json"}


def nepal_earthquakes(key: str, client: CachedWaveformClient) -> list[tuple[float, float]]:
    """Segment features for every usable corpus earthquake, recomputed from the cache."""
    site = STATION_SITES[key]
    manifest = json.loads((CORPUS / CORPUS_FILE[key]).read_text(encoding="utf-8"))
    out = []
    for ev in manifest["events"]:
        if ev["status"] != "ok" or ev.get("onset_s") is None:
            continue
        origin = datetime.fromisoformat(ev["origin_utc"])
        r = client.get_waveforms(
            WaveformRequest(
                site.site.network,
                site.site.station,
                site.site.location,
                site.site.channel,
                origin - timedelta(seconds=WINDOW_PRE_S),
                origin + timedelta(seconds=WINDOW_POST_S),
            )
        )
        if not r.ok:
            continue
        tr = r.stream.merge(fill_value="interpolate")[0]
        sr = float(tr.stats.sampling_rate)
        proc = preprocess(np.asarray(tr.data, dtype=float), sr)
        a = max(round(ev["onset_s"] * sr), 0)
        b = min(a + round(SEGMENT_S * sr), proc.size)
        if b - a < int(sr * 5):
            continue
        lf, cen = spectral_features(proc[a:b], sr)
        if math.isfinite(lf) and math.isfinite(cen):
            out.append((float(lf), float(cen)))
    return out


def _harvest_noise() -> Any:
    spec = importlib.util.spec_from_file_location(
        "harvest_noise", REPO_ROOT / "scripts" / "harvest_noise.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["harvest_noise"] = mod
    spec.loader.exec_module(mod)
    return mod


def noise_rows(key: str, client: CachedWaveformClient) -> tuple[list[dict[str, Any]], float]:
    """Usable noise windows with per trigger segment features, as exp018 builds them."""
    committed = json.loads((CORPUS / NOISE_FILE[key]).read_text(encoding="utf-8"))
    rows = [r for r in committed["windows"] if r["status"] == "ok"]
    if rows and "trigger_segments" not in rows[0]:
        hn = _harvest_noise()
        site = STATION_SITES[key]
        rows = [
            hn.process(datetime.fromisoformat(r["window_start_utc"]), client, site) for r in rows
        ]
        rows = [r for r in rows if r["status"] == "ok"]
    return rows, float(committed["window_s"])


def passes(lf: float, cen: float, lf_min: float, cen_max: float) -> bool:
    return math.isfinite(lf) and math.isfinite(cen) and lf >= lf_min and cen <= cen_max


def relative_cut(quakes: list[tuple[float, float]], q: float) -> tuple[float, float]:
    lf = np.array([x[0] for x in quakes])
    cen = np.array([x[1] for x in quakes])
    return float(np.quantile(lf, q)), float(np.quantile(cen, 1.0 - q))


def quake_pass_share(quakes: list[tuple[float, float]], q: float) -> float:
    """Each earthquake judged against the quantiles of the others."""
    hits = 0
    for i, (lf, cen) in enumerate(quakes):
        lf_min, cen_max = relative_cut(quakes[:i] + quakes[i + 1 :], q)
        hits += passes(lf, cen, lf_min, cen_max)
    return hits / len(quakes)


def noise_rate(
    rows: list[dict[str, Any]], window_s: float, lf_min: float, cen_max: float
) -> dict[str, Any]:
    alarms = 0
    for r in rows:
        if r.get("n_triggers", 0) <= 0:
            continue
        if any(
            s.get("signal_present")
            and passes(
                float(s.get("spectral_ratio_low_high", float("nan"))),
                float(s.get("spectral_centroid_hz", float("nan"))),
                lf_min,
                cen_max,
            )
            for s in r.get("trigger_segments", [])
        ):
            alarms += 1
    sm = len(rows) * window_s / 3600.0 / HOURS_PER_STATION_MONTH
    return {
        "windows": alarms,
        "station_months": round(sm, 3),
        "per_station_month": round(alarms / sm, 2),
    }


def main() -> int:
    client = CachedWaveformClient()
    records: dict[str, dict[str, Any]] = {}

    for key in ("NK.KKN", "IO.EVN"):
        quakes = nepal_earthquakes(key, client)
        rows, window_s = noise_rows(key, client)
        records[key] = {"event": "2026 Bhote Koshi", "event_values": CASCADE[key], "quakes": quakes}
        records[key]["noise"] = (rows, window_s)
        print(f"{key}: {len(quakes)} earthquakes, {len(rows)} noise windows", flush=True)

    swiss = json.loads(EXP031.read_text(encoding="utf-8"))
    for sta, entry in swiss["stations"].items():
        ev = entry["avalanche"]
        if ev.get("status") != "ok":
            continue
        quakes = [(q["lf_hf"], q["centroid_hz"]) for q in entry["earthquakes"]]
        records[f"CH.{sta}"] = {
            "event": "2017 Bondo",
            "event_values": (ev["lf_hf"], ev["centroid_hz"]),
            "quakes": quakes,
        }

    # The absolute rule as exp022 applies it: each Nepal station's own 2026 values with the
    # 20 percent margin. A Swiss station gets the live rule, NK.KKN's, as in exp031.
    margin = 0.2

    def absolute_cut(key: str) -> tuple[float, float]:
        lf, cen = CASCADE.get(key, CASCADE["NK.KKN"])
        return lf * (1 - margin), cen * (1 + margin)

    def absolute_block() -> dict[str, Any]:
        per: dict[str, Any] = {}
        for key, rec in records.items():
            lf, cen = rec["event_values"]
            qs = rec["quakes"]
            abs_lf, abs_cen = absolute_cut(key)
            row = {
                "lf_hf_min": round(abs_lf, 3),
                "centroid_max_hz": round(abs_cen, 3),
                "event_passes": passes(lf, cen, abs_lf, abs_cen),
                "quake_pass_share": round(
                    sum(passes(a, b, abs_lf, abs_cen) for a, b in qs) / len(qs), 3
                ),
            }
            if "noise" in rec:
                row["noise"] = noise_rate(*rec["noise"], abs_lf, abs_cen)
            per[key] = row
        return {
            "rule": "absolute: each Nepal station's 2026 values with a 20 percent margin; "
            "Swiss stations get NK.KKN's",
            "events_passed": sum(r["event_passes"] for r in per.values()),
            "stations": per,
        }

    sweep = []
    for q in QUANTILES:
        per: dict[str, Any] = {}
        for key, rec in records.items():
            lf, cen = rec["event_values"]
            lf_min, cen_max = relative_cut(rec["quakes"], q)
            row = {
                "lf_hf_min": round(lf_min, 3),
                "centroid_max_hz": round(cen_max, 3),
                "event_passes": passes(lf, cen, lf_min, cen_max),
                "quake_pass_share": round(quake_pass_share(rec["quakes"], q), 3),
                "n_quakes": len(rec["quakes"]),
            }
            if "noise" in rec:
                row["noise"] = noise_rate(*rec["noise"], lf_min, cen_max)
            per[key] = row
        sweep.append(
            {
                "quantile": q,
                "events_passed": sum(r["event_passes"] for r in per.values()),
                "stations": per,
            }
        )

    absolute = absolute_block()
    print(f"\nabsolute rule: {absolute['events_passed']} of {len(records)} station records")
    for key, r in absolute["stations"].items():
        extra = f"  noise {r['noise']['per_station_month']}/month" if "noise" in r else ""
        print(
            f"   {key:<9} event {r['event_passes']!s:<5} quakes {r['quake_pass_share']:.2f}{extra}"
        )
    for s in sweep:
        print(f"\nrelative q={s['quantile']:.2f}: {s['events_passed']} of {len(records)}")
        for key, r in s["stations"].items():
            extra = f"  noise {r['noise']['per_station_month']}/month" if "noise" in r else ""
            print(
                f"   {key:<9} event {r['event_passes']!s:<5} quakes {r['quake_pass_share']:.2f}"
                f"  (LF/HF >= {r['lf_hf_min']:.2f}, centroid <= {r['centroid_max_hz']:.2f}){extra}"
            )

    out = {
        "experiment": "exp032_relative_thresholds",
        "segment_s": SEGMENT_S,
        "records": {
            k: {
                "event": v["event"],
                "event_values": v["event_values"],
                "n_quakes": len(v["quakes"]),
            }
            for k, v in records.items()
        },
        "absolute": absolute,
        "relative_sweep": sweep,
        "note": "spectral layer only; the H/V, partner and catalogue rules are not applied",
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {HERE / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
