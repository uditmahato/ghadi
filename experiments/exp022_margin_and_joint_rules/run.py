"""Experiment 022: what does margin cost, and what do the rules remove together? (#32, #37)

**Question.** Every threshold so far is the 2026 event's own value, which has no margin
(exp020 showed the live path missing the event by 0.00002 Hz). Two new rules were priced
one at a time: two station agreement (exp019) and the horizontal to vertical energy
ratio (exp021). What is the false alarm rate when the thresholds are loosened by a
stated margin, and when the rules are applied together?

**Design.**

* **Margins** of 0, 10, 20, 30, and 50 percent. At margin m the spectral test accepts
  LF/HF at or above (1 - m) times the cascade's value and a centroid at or below
  (1 + m) times it, and the H/V test accepts a ratio at or above (1 - m) times the
  cascade's value. The 2026 event passes every rule at every margin by construction.
* **Corpora.** exp018's basis: IO.EVN from its committed corpus, NK.KKN reprocessed from
  the cache, one decision per trigger segment.
* **Rules,** applied per window (a window is a false alarm if any segment survives):
  spectral; spectral and H/V; spectral and the other station triggering at a fitting
  time for any source in the region; spectral and a fitting source inside an approximate
  basin box; all three together.
* **Rates** per station month with exact Poisson intervals, and the number of windows
  where the other station or the horizontals were unavailable, because a rule that
  cannot be applied is not a rule that passed.

The basin box is approximate: the upper Trishuli and Bhote Koshi catchment above Bidur,
27.95 to 28.45 N and 85.20 to 85.70 E. It stands in for a river geometry the repository
does not hold and is stated here so it can be replaced.

    python experiments/exp022_margin_and_joint_rules/run.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.associate import Pick, SearchRegion, arrival_bracket, feasible_grid  # noqa: E402
from ghadi.config import DEFAULT, EVEREST, KAKANI, STATION_SITES, Station, StationSite  # noqa: E402
from ghadi.detect import sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import preprocess  # noqa: E402
from ghadi.features_3c import hv_ratio  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402

CORPUS = REPO_ROOT / "data" / "corpus"
HOURS_PER_STATION_MONTH = 24 * 30.44
NOISE_WINDOW_S = 2100.0
MARGINS = (0.0, 0.1, 0.2, 0.3, 0.5)
REGION = SearchRegion(27.4, 29.0, 84.6, 86.6, step_km=4.0)
ZONE = (28.255, 85.520, 8.0)
BASIN_BOX = (27.95, 28.45, 85.20, 85.70)  # lat_min, lat_max, lon_min, lon_max, approximate
BASE = {
    "NK.KKN": {"lf_hf": 4.9188, "centroid_hz": 1.8852, "hv_segment": 2.3248},
    "IO.EVN": {"lf_hf": 15.0726, "centroid_hz": 1.5325, "hv_segment": 1.9805},
}
OTHER = {"NK.KKN": "IO.EVN", "IO.EVN": "NK.KKN"}
SITES: dict[str, StationSite] = {"NK.KKN": KAKANI, "IO.EVN": EVEREST}


def poisson_interval(k: int, conf: float = 0.95) -> tuple[float, float]:
    from scipy.stats import chi2

    a = 1 - conf
    lo = 0.0 if k == 0 else float(chi2.ppf(a / 2, 2 * k) / 2)
    hi = float(chi2.ppf(1 - a / 2, 2 * (k + 1)) / 2)
    return lo, hi


def rate_block(n: int, sm: float) -> dict[str, Any]:
    lo, hi = poisson_interval(n)
    return {
        "windows": n,
        "per_station_month": round(n / sm, 2),
        "ci95_per_station_month": [round(lo / sm, 2), round(hi / sm, 2)],
    }


def thresholds(station: str, m: float) -> dict[str, float]:
    b = BASE[station]
    return {
        "lf_hf_min": b["lf_hf"] * (1 - m),
        "centroid_hz_max": b["centroid_hz"] * (1 + m),
        "hv_min": b["hv_segment"] * (1 - m),
    }


def spectral_pass(seg: dict[str, Any], thr: dict[str, float]) -> bool:
    lf, cen = seg.get("spectral_ratio_low_high"), seg.get("spectral_centroid_hz")
    return bool(
        seg.get("signal_present")
        and isinstance(lf, int | float)
        and isinstance(cen, int | float)
        and np.isfinite(lf)
        and np.isfinite(cen)
        and lf >= thr["lf_hf_min"]
        and cen <= thr["centroid_hz_max"]
    )


def _harvest_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "harvest_noise", REPO_ROOT / "scripts" / "harvest_noise.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["harvest_noise"] = mod
    spec.loader.exec_module(mod)
    return mod


def corpus_rows(client: CachedWaveformClient) -> dict[str, tuple[list[dict[str, Any]], float]]:
    hn = _harvest_module()
    out: dict[str, tuple[list[dict[str, Any]], float]] = {}
    evn = json.loads((CORPUS / "noise_IO_EVN.json").read_text(encoding="utf-8"))
    out["IO.EVN"] = ([r for r in evn["windows"] if r["status"] == "ok"], evn["window_s"])
    nk = json.loads((CORPUS / "noise.json").read_text(encoding="utf-8"))
    rows = []
    for r in nk["windows"]:
        if r["status"] != "ok":
            continue
        new = hn.process(
            datetime.fromisoformat(r["window_start_utc"]), client, STATION_SITES["NK.KKN"]
        )
        if new["status"] == "ok":
            rows.append(new)
    out["NK.KKN"] = (rows, nk["window_s"])
    return out


def load(
    client: CachedWaveformClient, site: StationSite, channel: str, start: datetime, end: datetime
) -> tuple[np.ndarray | None, float]:
    st = Station(site.site.network, site.site.station, site.site.location, channel)
    result = client.get_waveforms(
        WaveformRequest(st.network, st.station, st.location, st.channel, start, end)
    )
    if not result.ok:
        return None, 0.0
    trace = result.stream.merge(fill_value="interpolate")[0]
    return np.asarray(trace.data, dtype=float), float(trace.stats.sampling_rate)


def in_box(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    return (
        (lats >= BASIN_BOX[0])
        & (lats <= BASIN_BOX[1])
        & (lons >= BASIN_BOX[2])
        & (lons <= BASIN_BOX[3])
    )


def examine_window(
    client: CachedWaveformClient, station: str, row: dict[str, Any], loosest: dict[str, float]
) -> dict[str, Any]:
    """Everything the rules need for one candidate window, fetched once."""
    site, other = SITES[station], SITES[OTHER[station]]
    start = datetime.fromisoformat(row["window_start_utc"])
    end = start + timedelta(seconds=NOISE_WINDOW_S)
    rec: dict[str, Any] = {"window_start_utc": row["window_start_utc"], "segments": []}

    z, sr = load(client, site, site.site.channel, start, end)
    n, _ = load(client, site, site.site.channel[:2] + "N", start, end)
    e, _ = load(client, site, site.site.channel[:2] + "E", start, end)
    have_3c = z is not None and n is not None and e is not None
    rec["horizontals_available"] = have_3c
    if have_3c:
        assert z is not None and n is not None and e is not None
        m = min(z.size, n.size, e.size)
        pz, pn, pe = preprocess(z[:m], sr), preprocess(n[:m], sr), preprocess(e[:m], sr)

    oz, osr = load(client, other, other.site.channel, start, end)
    rec["other_station_available"] = oz is not None
    other_triggers: list[Any] = []
    if oz is not None:
        other_triggers = list(sta_lta(preprocess(oz, osr), osr, preprocessed=True).triggers)

    for seg in row.get("trigger_segments", []):
        if not spectral_pass(seg, loosest):
            continue
        s: dict[str, Any] = {
            "on_s": seg["on_s"],
            "lf_hf": seg["spectral_ratio_low_high"],
            "centroid_hz": seg["spectral_centroid_hz"],
            "hv_segment": None,
            "other_any_source": False,
            "other_zone": False,
            "other_basin_box": False,
        }
        if have_3c:
            a = max(round(seg["on_s"] * sr), 0)
            b = min(a + round(DEFAULT.seismic.decision_segment_s * sr), pz.size)
            if b - a > 2:
                v = hv_ratio(pz[a:b], pn[a:b], pe[a:b])
                s["hv_segment"] = None if not np.isfinite(v) else round(float(v), 4)
        if oz is not None:
            onset = start + timedelta(seconds=seg["on_s"])
            pick = Pick(station, site.latitude, site.longitude, onset)
            lo, hi = arrival_bracket(pick, other.latitude, other.longitude, REGION)
            for trig in other_triggers:
                when = start + timedelta(seconds=trig.on_s)
                if not (lo <= when <= hi):
                    continue
                s["other_any_source"] = True
                other_pick = Pick(OTHER[station], other.latitude, other.longitude, when)
                first, second = (pick, other_pick) if station == "NK.KKN" else (other_pick, pick)
                lats, lons, mask = feasible_grid(first, second, REGION)
                zone = (
                    np.array(
                        [
                            haversine_km(float(la), float(lo_), ZONE[0], ZONE[1])
                            for la, lo_ in zip(lats, lons, strict=True)
                        ]
                    )
                    <= ZONE[2]
                )
                if bool((mask & zone).any()):
                    s["other_zone"] = True
                if bool((mask & in_box(lats, lons)).any()):
                    s["other_basin_box"] = True
        rec["segments"].append(s)
    return rec


def count_rules(windows: list[dict[str, Any]], thr: dict[str, float]) -> dict[str, int]:
    names = (
        "spectral",
        "spectral_hv",
        "spectral_two_station_any",
        "spectral_two_station_basin",
        "spectral_hv_two_station_basin",
    )
    counts = dict.fromkeys(names, 0)
    counts["hv_unavailable_among_spectral"] = 0
    counts["other_unavailable_among_spectral"] = 0
    for w in windows:
        segs = [
            s
            for s in w["segments"]
            if s["lf_hf"] >= thr["lf_hf_min"] and s["centroid_hz"] <= thr["centroid_hz_max"]
        ]
        if not segs:
            continue
        counts["spectral"] += 1
        if not w["horizontals_available"]:
            counts["hv_unavailable_among_spectral"] += 1
        if not w["other_station_available"]:
            counts["other_unavailable_among_spectral"] += 1
        hv_ok = [
            s for s in segs if s["hv_segment"] is not None and s["hv_segment"] >= thr["hv_min"]
        ]
        if hv_ok:
            counts["spectral_hv"] += 1
        if any(s["other_any_source"] for s in segs):
            counts["spectral_two_station_any"] += 1
        if any(s["other_basin_box"] for s in segs):
            counts["spectral_two_station_basin"] += 1
        if any(s["other_basin_box"] for s in hv_ok):
            counts["spectral_hv_two_station_basin"] += 1
    return counts


def main() -> int:
    client = CachedWaveformClient()
    corpora = corpus_rows(client)
    results: dict[str, Any] = {
        "experiment": "exp022_margin_and_joint_rules",
        "margins": list(MARGINS),
        "base_thresholds": BASE,
        "basin_box": BASIN_BOX,
        "zone": ZONE,
        "stations": {},
    }
    for station, (rows, window_s) in corpora.items():
        sm = len(rows) * window_s / 3600.0 / HOURS_PER_STATION_MONTH
        loosest = thresholds(station, max(MARGINS))
        candidates = [
            r for r in rows if any(spectral_pass(s, loosest) for s in r.get("trigger_segments", []))
        ]
        print(
            f"{station}: {len(rows)} usable windows, {sm:.3f} sm, "
            f"{len(candidates)} candidates at margin {max(MARGINS)}",
            flush=True,
        )
        examined = []
        for i, r in enumerate(candidates, 1):
            examined.append(examine_window(client, station, r, loosest))
            if i % 10 == 0:
                print(f"   {i}/{len(candidates)}", flush=True)
        by_margin = {}
        for m in MARGINS:
            thr = thresholds(station, m)
            counts = count_rules(examined, thr)
            by_margin[str(m)] = {
                "thresholds": {k: round(v, 4) for k, v in thr.items()},
                **{
                    k: (rate_block(v, sm) if not k.endswith("among_spectral") else v)
                    for k, v in counts.items()
                },
            }
        results["stations"][station] = {
            "station_months": round(sm, 3),
            "usable_windows": len(rows),
            "candidate_windows": len(candidates),
            "by_margin": by_margin,
            "windows": examined,
        }
        print(f"\n{station} ({sm:.3f} station months)")
        cols = (
            "spectral",
            "spectral_hv",
            "spectral_two_station_any",
            "spectral_two_station_basin",
            "spectral_hv_two_station_basin",
        )
        print("  margin " + " ".join(f"{c[:14]:>14}" for c in cols) + "   hv n/a other n/a")
        for m, rec in by_margin.items():
            rates = " ".join(f"{rec[c]['per_station_month']:>14.2f}" for c in cols)
            print(
                f"  {float(m):>6.1f} {rates}   {rec['hv_unavailable_among_spectral']:>5d} "
                f"{rec['other_unavailable_among_spectral']:>9d}"
            )
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
