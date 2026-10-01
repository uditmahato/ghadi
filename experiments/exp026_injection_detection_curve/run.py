"""Experiment 026: how small an event would the system still catch?

**Question.** Every number so far is on the false alarm side. With one real event the
miss side cannot be counted. It can be estimated: take the 2026 waveform, scale it down,
add it to real noise recorded at the same station, and see how often the decision the
live loop makes still comes out "mass movement like". That gives a detection
probability against signal strength, and prices the margin and each rule from the miss
side.

**Design.**

* **Template.** The 2026 event at NK.KKN on all three components and at IO.EVN on the
  vertical, from 3 s before the picked onset to 200 s after, mean removed and tapered.
* **Noise.** A fixed random sample of the NK.KKN noise corpus (exp009), with the
  horizontals and the IO.EVN vertical fetched for the same windows. These windows
  contain no catalogued earthquake.
* **Injection.** The template times a factor is added to each noise window, the IO.EVN
  copy 12.8 s later as observed in 2026 (exp019). Factors run from the full 2026
  amplitude down to 2 percent of it, and a factor of zero is the control.
* **Decision.** ``ghadi.live.observation_from_window``, the function the shadow service
  calls, on the 240 s window that holds the injected onset at 90 s, with horizontals.
  Detected means a trigger within 15 s of the injected onset whose segment classifies as
  mass movement like at the default thresholds (20 percent margin, H/V rule on).
* **Stages.** For each factor: trigger found; spectral test passed; H/V passed;
  detected; and whether IO.EVN triggered at a fitting time (corroboration).
* **Margin.** The same injections are classified at zero margin too, so the margin's
  value on the miss side can be read off.

A scaled copy of one event is not a population of events. This measures sensitivity to
*size* for an event shaped like 2026 at these distances. It says nothing about events
of a different shape.

    python experiments/exp026_injection_detection_curve/run.py
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.associate import Pick, arrival_bracket  # noqa: E402
from ghadi.classify import classify_segment  # noqa: E402
from ghadi.config import DEFAULT, EVEREST, KAKANI, Station, StationSite  # noqa: E402
from ghadi.detect import pick_onset, sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import preprocess  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402
from ghadi.live import DEFAULT_REGION, LiveConfig, observation_from_window  # noqa: E402
from ghadi.stream import StreamWindow  # noqa: E402

CORPUS = REPO_ROOT / "data" / "corpus" / "noise.json"
ORIGIN = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)
ZONE = (28.255, 85.520)
N_WINDOWS = 120
SEED = 26
FACTORS = (0.0, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2, 0.3, 0.5, 1.0)
INJECT_AT_S = 600.0  # where in the 2100 s noise window the onset goes
ONSET_IN_SLICE_S = 90.0
# The template starts just before the onset. An earlier start carries the 2026
# background noise with it, and at full size that alone trips the detector 15 s early
# in a quieter window, which is the template's doing and not the event's.
PRE_S, POST_S = 3.0, 200.0
PARTNER_LAG_S = 12.78
TOLERANCE_S = 15.0
ZERO_MARGIN = replace(
    DEFAULT.classify,
    cascade_segment_lf_hf=4.9188,
    cascade_segment_centroid_hz=1.8852,
    segment_hv_min=2.3248,
)


def load(
    client: CachedWaveformClient, site: StationSite, comp: str, start: datetime, end: datetime
) -> tuple[np.ndarray | None, float]:
    st = Station(
        site.site.network, site.site.station, site.site.location, site.site.channel[:2] + comp
    )
    r = client.get_waveforms(
        WaveformRequest(st.network, st.station, st.location, st.channel, start, end)
    )
    if not r.ok:
        return None, 0.0
    tr = r.stream.merge(fill_value="interpolate")[0]
    return np.asarray(tr.data, dtype=float), float(tr.stats.sampling_rate)


def taper(x: np.ndarray, sr: float, seconds: float = 5.0) -> np.ndarray:
    n = min(round(seconds * sr), x.size // 2)
    w = np.ones(x.size)
    ramp = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
    w[:n], w[-n:] = ramp, ramp[::-1]
    return x * w


def template(
    client: CachedWaveformClient, site: StationSite, comps: str, pre: float, post: float
) -> dict[str, Any]:
    start, end = ORIGIN - timedelta(seconds=pre), ORIGIN + timedelta(seconds=post)
    z, sr = load(client, site, "Z", start, end)
    if z is None:
        raise SystemExit(f"no 2026 waveform for {site.key}")
    det = sta_lta(preprocess(z, sr), sr, preprocessed=True)
    distance = haversine_km(site.latitude, site.longitude, *ZONE)
    pick = pick_onset(det.triggers, origin_offset_s=pre, distance_km=distance)
    if not pick.ok or pick.onset_s is None:
        raise SystemExit(f"no 2026 onset at {site.key}: {pick.reason}")
    a = round((pick.onset_s - PRE_S) * sr)
    b = round((pick.onset_s + POST_S) * sr)
    out: dict[str, Any] = {"sr": sr, "onset_s": pick.onset_s}
    for comp in comps:
        data = z if comp == "Z" else load(client, site, comp, start, end)[0]
        if data is None:
            raise SystemExit(f"no 2026 {comp} component at {site.key}")
        seg = data[a:b] - np.mean(data[a:b])
        out[comp] = taper(seg, sr, seconds=PRE_S)
    return out


def inject(
    noise: np.ndarray, tpl: np.ndarray, sr: float, onset_s: float, factor: float
) -> np.ndarray:
    out = noise.astype(float).copy()
    a = round((onset_s - PRE_S) * sr)
    b = min(a + tpl.size, out.size)
    if a < 0 or b <= a:
        return out
    out[a:b] += factor * tpl[: b - a]
    return out


def main() -> int:
    client = CachedWaveformClient()
    tpl_k = template(client, KAKANI, "ZNE", 600.0, 2100.0)
    tpl_e = template(client, EVEREST, "Z", 600.0, 1500.0)
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    ok = [w for w in corpus["windows"] if w["status"] == "ok"]
    random.Random(SEED).shuffle(ok)
    live = LiveConfig(station="NK.KKN")
    seg_s = DEFAULT.seismic.decision_segment_s
    rows: list[dict[str, Any]] = []
    used = 0
    for w in ok:
        if used >= N_WINDOWS:
            break
        start = datetime.fromisoformat(w["window_start_utc"])
        end = start + timedelta(seconds=corpus["window_s"])
        z, sr = load(client, KAKANI, "Z", start, end)
        n, _ = load(client, KAKANI, "N", start, end)
        e, _ = load(client, KAKANI, "E", start, end)
        if z is None or n is None or e is None or abs(sr - tpl_k["sr"]) > 1e-9:
            continue
        m = min(z.size, n.size, e.size)
        if m < round((INJECT_AT_S + POST_S + 60) * sr):
            continue
        pz, sr_e = load(client, EVEREST, "Z", start, end)
        if pz is not None and abs(sr_e - tpl_e["sr"]) > 1e-9:
            pz = None
        used += 1
        slice_start_s = INJECT_AT_S - ONSET_IN_SLICE_S
        a = round(slice_start_s * sr)
        b = a + round(DEFAULT.seismic.window_s * sr)
        onset_utc = start + timedelta(seconds=INJECT_AT_S)
        for f in FACTORS:
            zi = inject(z[:m], tpl_k["Z"], sr, INJECT_AT_S, f)
            ni = inject(n[:m], tpl_k["N"], sr, INJECT_AT_S, f)
            ei = inject(e[:m], tpl_k["E"], sr, INJECT_AT_S, f)
            win = StreamWindow(
                station="NK.KKN",
                start_utc=start + timedelta(seconds=slice_start_s),
                end_utc=start + timedelta(seconds=slice_start_s + DEFAULT.seismic.window_s),
                sampling_rate=sr,
                data=zi[a:b],
                gap_fraction=0.0,
                n_packets=24,
                max_delay_s=6.0,
            )
            rec: dict[str, Any] = {"window_start_utc": w["window_start_utc"], "factor": f}
            slice_det = sta_lta(preprocess(zi[a:b], sr), sr, preprocessed=True)
            trig_any = any(
                abs(t.on_s - ONSET_IN_SLICE_S) <= TOLERANCE_S for t in slice_det.triggers
            )
            for name, cfg in (
                ("margin20", DEFAULT),
                ("margin0", replace(DEFAULT, classify=ZERO_MARGIN)),
            ):
                v = observation_from_window(
                    win,
                    live=live,
                    config=cfg,
                    feed_time=win.end_utc,
                    horizontals=(ni[a:b], ei[a:b]),
                )
                o = v.observation
                near = (
                    o is not None
                    and abs((o.detected_utc - onset_utc).total_seconds()) <= TOLERANCE_S
                )
                trig = bool(trig_any)
                spectral = hv_ok = like = False
                if near and o is not None:
                    c = cfg.classify
                    spectral = (
                        o.segment_lf_hf >= c.cascade_segment_lf_hf
                        and o.segment_centroid_hz <= c.cascade_segment_centroid_hz
                    )
                    hv_ok = (
                        o.segment_hv is not None
                        and c.segment_hv_min is not None
                        and (o.segment_hv >= c.segment_hv_min)
                    )
                    like = classify_segment(
                        o.segment_lf_hf, o.segment_centroid_hz, config=c, segment_hv=o.segment_hv
                    ).mass_movement_like
                rec[name] = {
                    "trigger": trig,
                    "spectral": bool(spectral),
                    "hv": bool(hv_ok),
                    "detected": bool(like),
                    "lf_hf": None if o is None else round(float(o.segment_lf_hf), 3),
                    "centroid_hz": None if o is None else round(float(o.segment_centroid_hz), 3),
                    "hv_value": None
                    if o is None or o.segment_hv is None
                    else round(o.segment_hv, 3),
                }
            # Partner: does IO.EVN trigger at a fitting time?
            rec["partner_available"] = pz is not None
            rec["partner_corroborates"] = None
            if pz is not None:
                pi = inject(pz, tpl_e["Z"], sr_e, INJECT_AT_S + PARTNER_LAG_S, f)
                pa = round(slice_start_s * sr_e)
                pb = pa + round(DEFAULT.seismic.window_s * sr_e)
                det = sta_lta(preprocess(pi[pa:pb], sr_e), sr_e, preprocessed=True)
                pick = Pick("NK.KKN", KAKANI.latitude, KAKANI.longitude, onset_utc)
                lo, hi = arrival_bracket(pick, EVEREST.latitude, EVEREST.longitude, DEFAULT_REGION)
                slice_utc = start + timedelta(seconds=slice_start_s)
                rec["partner_corroborates"] = any(
                    lo <= slice_utc + timedelta(seconds=t.on_s) <= hi for t in det.triggers
                )
            rows.append(rec)
        if used % 20 == 0:
            print(f"   {used} windows", flush=True)

    summary: dict[str, Any] = {}
    for f in FACTORS:
        sub = [r for r in rows if r["factor"] == f]
        n_sub = len(sub)
        part = [r for r in sub if r["partner_available"]]
        entry: dict[str, Any] = {"windows": n_sub}
        for name in ("margin20", "margin0"):
            entry[name] = {
                k: round(sum(r[name][k] for r in sub) / n_sub, 3)
                for k in ("trigger", "spectral", "hv", "detected")
            }
        entry["partner_windows"] = len(part)
        entry["partner_corroborates"] = (
            round(sum(bool(r["partner_corroborates"]) for r in part) / len(part), 3)
            if part
            else None
        )
        entry["detected_and_corroborated_margin20"] = (
            round(
                sum(r["margin20"]["detected"] and bool(r["partner_corroborates"]) for r in part)
                / len(part),
                3,
            )
            if part
            else None
        )
        summary[str(f)] = entry
    results = {
        "experiment": "exp026_injection_detection_curve",
        "windows_used": used,
        "factors": list(FACTORS),
        "segment_s": seg_s,
        "template": {"NK.KKN_onset_s": tpl_k["onset_s"], "IO.EVN_onset_s": tpl_e["onset_s"]},
        "summary": summary,
        "rows": rows,
    }
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"{used} noise windows")
    print("factor  trigger spectral    hv detected(20%)  detected(0%)  partner  both")
    for f, e in summary.items():
        m20, m0 = e["margin20"], e["margin0"]
        print(
            f"{float(f):6.2f}  {m20['trigger']:7.2f} {m20['spectral']:8.2f} {m20['hv']:5.2f} "
            f"{m20['detected']:13.2f} {m0['detected']:13.2f}  {e['partner_corroborates']}  "
            f"{e['detected_and_corroborated_margin20']}"
        )
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
