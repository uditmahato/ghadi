"""Experiment 034: how much do the segment features depend on where the segment starts?

Every decision so far is made on 120 s of signal starting at a trigger. For an emergent
source the trigger can fire on the first weak arrival or on the strong waves that come
later, and exp031 found two Bondo stations at the same distance giving very different
LF/HF because one triggered on the first arrival. exp033 found an unrelated earthquake
corrupting onsets until the first trigger after the catalogue origin was used. A reviewer
will ask how sensitive the features are to the segment start.

For each mass movement record (the 2026 event on NK.KKN and IO.EVN, Bondo on five Swiss
stations, Taan Fiord on six Alaska stations) this:

* slides the 120 s segment from 30 s before to 90 s after the first trigger, in 5 s
  steps, and records LF/HF (below and above 3 Hz), the spectral centroid and H/V;
* applies five segment start rules to the event and, the same way, to every earthquake
  on the same station: the first trigger, the first trigger plus 30 s, the strongest
  trigger, the envelope peak minus 30 s, and a 180 s segment from the first trigger;
* judges each with the live Nepal rule and with exp032's station relative rule (the
  0.80 quantile of that station's earthquakes, measured with the same start rule).

The decision code is not changed. Everything reads the cache; offline is fine.

    python experiments/exp034_onset_sensitivity/run.py
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.classify import classify_segment  # noqa: E402
from ghadi.config import DEFAULT, STATION_SITES, StationSite  # noqa: E402
from ghadi.detect import Trigger, pick_onset, sta_lta  # noqa: E402
from ghadi.detect.onset import DEFAULT_TOLERANCE_S  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import envelope, extract, preprocess, spectral_features  # noqa: E402
from ghadi.features_3c import hv_ratio  # noqa: E402
from ghadi.geo import haversine_km, p_travel_time_s  # noqa: E402

HERE = Path(__file__).resolve().parent
EXPERIMENTS = REPO_ROOT / "experiments"
CORPUS = REPO_ROOT / "data" / "corpus"


def _module(name: str, path: Path) -> ModuleType:
    """Another experiment's run.py, for its loader and settings. Its main() is not run."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


BONDO = _module("exp031_run", EXPERIMENTS / "exp031_bondo_outside_event" / "run.py")
TAAN = _module("exp033_run", EXPERIMENTS / "exp033_taan_fiord_outside_event" / "run.py")

SEGMENT_S = DEFAULT.seismic.decision_segment_s
LONG_SEGMENT_S = 180.0
SWEEP_OFFSETS_S = tuple(float(x) for x in range(-30, 95, 5))
DELAY_S = 30.0  # the fixed delay after the first trigger
PEAK_SEARCH_S = 120.0  # the envelope peak is looked for this long after the first trigger
PEAK_OFFSET_S = 30.0  # and the segment starts this long before it, never before the trigger
SMOOTH_S = DEFAULT.seismic.sta_s  # envelope smoothing, the STA length
QUANTILE = 0.80  # exp032's relative rule

# The 2026 event: windows as exp005 (NK.KKN) and exp010 (IO.EVN). The horizontals for
# NK.KKN are cached only on exp021's longer window, so they are cut to the vertical's.
NEPAL_ORIGIN = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)
NEPAL_SOURCE = (28.255, 85.520)
NEPAL_PRE_S, NEPAL_POST_S = 600.0, 1500.0
NEPAL_HORIZONTAL_POST_S = {"NK.KKN": 2100.0, "IO.EVN": 1500.0}
NEPAL_EVENT_SEARCH_S = (0.0, 240.0)  # the first trigger after the origin, as exp033
NEPAL_CORPUS = {"NK.KKN": "earthquakes.json", "IO.EVN": "earthquakes_IO_EVN.json"}

RULES = (
    "first_trigger",
    "first_trigger_plus_30s",
    "strongest_trigger",
    "envelope_peak_minus_30s",
    "first_trigger_180s",
)
RULE_TEXT = {
    "first_trigger": "120 s from the first trigger (the live rule)",
    "first_trigger_plus_30s": "120 s from 30 s after the first trigger",
    "strongest_trigger": "120 s from the trigger with the highest STA/LTA in the search window",
    "envelope_peak_minus_30s": (
        "120 s from 30 s before the peak of the smoothed envelope in the 120 s after the "
        "first trigger, never before the trigger"
    ),
    "first_trigger_180s": "180 s from the first trigger",
}


@dataclass(frozen=True)
class Window:
    """One preprocessed record and the triggers that may belong to its event."""

    z: np.ndarray
    n: np.ndarray | None
    e: np.ndarray | None
    sr: float
    candidates: tuple[Trigger, ...]  # in time order
    search_end_s: float  # the end of the span the candidates were taken from
    smooth_env: np.ndarray


def prepare(
    z: np.ndarray,
    n: np.ndarray | None,
    e: np.ndarray | None,
    sr: float,
    search: tuple[float, float],
) -> Window | None:
    proc = preprocess(z, sr)
    det = sta_lta(proc, sr, preprocessed=True)
    cands = tuple(
        sorted((t for t in det.triggers if search[0] <= t.on_s <= search[1]), key=lambda t: t.on_s)
    )
    if not cands:
        return None
    k = max(round(SMOOTH_S * sr), 1)
    smooth = np.convolve(envelope(proc), np.ones(k) / k, mode="same")
    pn = preprocess(n, sr) if n is not None else None
    pe = preprocess(e, sr) if e is not None else None
    return Window(proc, pn, pe, sr, cands, search[1], smooth)


def measure(w: Window, start_s: float, length_s: float) -> dict[str, Any] | None:
    """LF/HF, centroid and H/V over ``length_s`` from ``start_s``; None if it does not fit."""
    a = round(start_s * w.sr)
    b = a + round(length_s * w.sr)
    if a < 0 or b > w.z.size:
        return None
    if length_s == SEGMENT_S:
        seg = extract(w.z, w.sr, preprocessed=True, onset_s=start_s, segment_s=length_s)
        lf, cen = float(seg.spectral_ratio_low_high), float(seg.spectral_centroid_hz)
    else:
        lf, cen = spectral_features(w.z[a:b], w.sr)
    if not (math.isfinite(lf) and math.isfinite(cen)):
        return None
    hv = None
    if w.n is not None and w.e is not None:
        v = hv_ratio(w.z[a:b], w.n[a:b], w.e[a:b])
        hv = float(v) if math.isfinite(v) else None
    full = classify_segment(lf, cen, segment_hv=hv).mass_movement_like
    spectral = classify_segment(lf, cen).mass_movement_like
    return {
        "lf_hf": lf,
        "centroid_hz": cen,
        "hv": hv,
        "nepal_full": full,
        "nepal_spectral": spectral,
    }


def place(rule: str, w: Window) -> dict[str, float]:
    """Where a rule starts the segment, how long it is, and the latest time it looks at."""
    first = w.candidates[0]
    t1 = first.on_s
    if rule == "first_trigger":
        return {"t1": t1, "start": t1, "length": SEGMENT_S, "horizon": t1}
    if rule == "first_trigger_plus_30s":
        return {"t1": t1, "start": t1 + DELAY_S, "length": SEGMENT_S, "horizon": t1}
    if rule == "strongest_trigger":
        best = max(w.candidates, key=lambda t: t.peak_ratio)
        # Knowing it is the strongest needs the whole search span, which is anchored on
        # the catalogue origin, and the chosen trigger to have closed.
        horizon = max(w.search_end_s, max(t.off_s for t in w.candidates))
        return {"t1": t1, "start": best.on_s, "length": SEGMENT_S, "horizon": horizon}
    if rule == "envelope_peak_minus_30s":
        a = round(t1 * w.sr)
        b = min(a + round(PEAK_SEARCH_S * w.sr), w.smooth_env.size)
        peak = (a + int(np.argmax(w.smooth_env[a:b]))) / w.sr
        start = max(t1, peak - PEAK_OFFSET_S)
        return {"t1": t1, "start": start, "length": SEGMENT_S, "horizon": t1 + PEAK_SEARCH_S}
    if rule == "first_trigger_180s":
        return {"t1": t1, "start": t1, "length": LONG_SEGMENT_S, "horizon": t1}
    raise ValueError(rule)


def apply_rules(w: Window) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rule in RULES:
        p = place(rule, w)
        m = measure(w, p["start"], p["length"])
        if m is None:
            continue
        end = p["start"] + p["length"]
        out[rule] = {
            **m,
            "start_after_first_trigger_s": p["start"] - p["t1"],
            "decision_after_first_trigger_s": max(end, p["horizon"]) - p["t1"],
            "looks_past_segment_end_s": max(p["horizon"] - end, 0.0),
        }
    return out


def sweep(w: Window) -> dict[float, dict[str, Any]]:
    t1 = w.candidates[0].on_s
    out = {}
    for off in SWEEP_OFFSETS_S:
        m = measure(w, t1 + off, SEGMENT_S)
        if m is not None:
            out[off] = m
    return out


@dataclass
class Record:
    """One station's view of one mass movement, and that station's earthquakes."""

    key: str
    event: str
    distance_km: float
    onset_utc: str | None
    event_rules: dict[str, dict[str, Any]]
    event_sweep: dict[float, dict[str, Any]]
    quake_rules: list[dict[str, dict[str, Any]]]
    quake_sweep: list[dict[float, dict[str, Any]]]
    quakes_first_is_labelled: int
    has_quake_hv: bool


def quake_window(
    z: np.ndarray,
    n: np.ndarray | None,
    e: np.ndarray | None,
    sr: float,
    origin_s: float,
    distance_km: float,
) -> tuple[Window | None, bool]:
    """An earthquake's candidates: after its origin and near its predicted P arrival.

    The second value says whether the first candidate is the trigger ``pick_onset``
    labels, which every earlier experiment used.
    """
    det = sta_lta(preprocess(z, sr), sr, preprocessed=True)
    pick = pick_onset(det.triggers, origin_offset_s=origin_s, distance_km=distance_km)
    if not pick.ok or pick.onset_s is None:
        return None, False
    pred = origin_s + p_travel_time_s(distance_km)
    search = (max(origin_s, pred - DEFAULT_TOLERANCE_S), pred + DEFAULT_TOLERANCE_S)
    w = prepare(z, n, e, sr, search)
    if w is None:
        return None, False
    return w, abs(w.candidates[0].on_s - pick.onset_s) < 1e-9


# --- Nepal ---------------------------------------------------------------------------


def nepal_trace(
    client: CachedWaveformClient, site: StationSite, channel: str, start: datetime, end: datetime
) -> Any:
    r = client.get_waveforms(
        WaveformRequest(
            site.site.network, site.site.station, site.site.location, channel, start, end
        )
    )
    if not r.ok:
        return None
    return r.stream.merge(fill_value="interpolate")[0]


def nepal_record(client: CachedWaveformClient, key: str) -> Record:
    site = STATION_SITES[key]
    dist = haversine_km(site.latitude, site.longitude, *NEPAL_SOURCE)
    start = NEPAL_ORIGIN - timedelta(seconds=NEPAL_PRE_S)
    ztr = nepal_trace(
        client, site, site.site.channel, start, NEPAL_ORIGIN + timedelta(seconds=NEPAL_POST_S)
    )
    if ztr is None:
        raise SystemExit(f"2026 window not cached for {key}")
    sr = float(ztr.stats.sampling_rate)
    z = np.asarray(ztr.data, dtype=float)
    # Onsets are measured from the start of the vertical trace, as exp005 and exp010 did.
    origin_s = (NEPAL_ORIGIN - ztr.stats.starttime.datetime.replace(tzinfo=UTC)).total_seconds()
    horiz: list[np.ndarray | None] = []
    hend = NEPAL_ORIGIN + timedelta(seconds=NEPAL_HORIZONTAL_POST_S[key])
    for comp in ("N", "E"):
        tr = nepal_trace(client, site, site.site.channel[:2] + comp, start, hend)
        if tr is None:
            horiz.append(None)
            continue
        tr.trim(ztr.stats.starttime, ztr.stats.endtime, nearest_sample=True)
        if abs(tr.stats.starttime - ztr.stats.starttime) > 0.5 / sr:
            horiz.append(None)
            continue
        horiz.append(np.asarray(tr.data, dtype=float))
    m = min([z.size] + [h.size for h in horiz if h is not None])
    hn, he = (h[:m] if h is not None else None for h in horiz)
    search = (origin_s + NEPAL_EVENT_SEARCH_S[0], origin_s + NEPAL_EVENT_SEARCH_S[1])
    w = prepare(z[:m], hn, he, sr, search)
    if w is None:
        raise SystemExit(f"no trigger for the 2026 event on {key}")
    onset = ztr.stats.starttime.datetime.replace(tzinfo=UTC) + timedelta(
        seconds=w.candidates[0].on_s
    )

    manifest = json.loads((CORPUS / NEPAL_CORPUS[key]).read_text(encoding="utf-8"))
    q_rules, q_sweep, same = [], [], 0
    for ev in manifest["events"]:
        if ev["status"] != "ok" or ev.get("onset_s") is None:
            continue
        origin = datetime.fromisoformat(ev["origin_utc"])
        tr = nepal_trace(
            client,
            site,
            site.site.channel,
            origin - timedelta(seconds=NEPAL_PRE_S),
            origin + timedelta(seconds=NEPAL_POST_S),
        )
        if tr is None:
            continue
        o_s = (origin - tr.stats.starttime.datetime.replace(tzinfo=UTC)).total_seconds()
        # The corpus has the vertical only; its horizontals were never fetched.
        qw, is_same = quake_window(
            np.asarray(tr.data, dtype=float),
            None,
            None,
            float(tr.stats.sampling_rate),
            o_s,
            float(ev["distance_km"]),
        )
        if qw is None:
            continue
        rules = apply_rules(qw)
        if "first_trigger" not in rules:
            continue
        q_rules.append(rules)
        q_sweep.append(sweep(qw))
        same += is_same
    return Record(
        key,
        "2026 Bhote Koshi",
        dist,
        onset.isoformat(),
        apply_rules(w),
        sweep(w),
        q_rules,
        q_sweep,
        same,
        False,
    )


# --- Bondo and Taan Fiord --------------------------------------------------------------


def outside_record(
    client: CachedWaveformClient, mod: ModuleType, station: str, event: str
) -> Record:
    lat, lon = mod.STATIONS[station]
    key = f"{mod.NETWORK}.{station}"
    dist = haversine_km(lat, lon, mod.SOURCE_LAT, mod.SOURCE_LON)
    start = mod.EVENT_UTC - timedelta(seconds=mod.PRE_S)
    data = mod.load(client, station, start, mod.EVENT_UTC + timedelta(seconds=mod.POST_S))
    w = None
    if data is not None:
        lo, hi = mod.EVENT_SEARCH_S
        w = prepare(*data, (mod.PRE_S + lo, mod.PRE_S + hi))
    onset = None if w is None else (start + timedelta(seconds=w.candidates[0].on_s)).isoformat()

    q_rules, q_sweep, same = [], [], 0
    for quake in mod.catalogue():
        origin = datetime.fromisoformat(quake["origin_utc"])
        qd = mod.load(
            client,
            station,
            origin - timedelta(seconds=mod.PRE_S),
            origin + timedelta(seconds=mod.POST_S),
        )
        if qd is None:
            continue
        qdist = haversine_km(lat, lon, quake["lat"], quake["lon"])
        qw, is_same = quake_window(*qd, mod.PRE_S, qdist)
        if qw is None:
            continue
        rules = apply_rules(qw)
        if "first_trigger" not in rules:
            continue
        q_rules.append(rules)
        q_sweep.append(sweep(qw))
        same += is_same
    return Record(
        key,
        event,
        dist,
        onset,
        {} if w is None else apply_rules(w),
        {} if w is None else sweep(w),
        q_rules,
        q_sweep,
        same,
        True,
    )


# --- judging --------------------------------------------------------------------------


def relative_cut(rows: list[dict[str, Any]]) -> tuple[float, float]:
    lf = np.array([r["lf_hf"] for r in rows])
    cen = np.array([r["centroid_hz"] for r in rows])
    return float(np.quantile(lf, QUANTILE)), float(np.quantile(cen, 1.0 - QUANTILE))


def relative_pass(row: dict[str, Any], cut: tuple[float, float]) -> bool:
    return bool(row["lf_hf"] >= cut[0] and row["centroid_hz"] <= cut[1])


def loo_share(rows: list[dict[str, Any]]) -> float:
    """Each earthquake judged against the quantiles of the others (exp032)."""
    hits = sum(relative_pass(r, relative_cut(rows[:i] + rows[i + 1 :])) for i, r in enumerate(rows))
    return hits / len(rows)


def r3(x: float | None) -> float | None:
    return None if x is None else round(float(x), 3)


def judged(event_row: dict[str, Any] | None, quakes: list[dict[str, Any]]) -> dict[str, Any]:
    """The event's values and both rules' verdicts, and the earthquakes' pass shares."""
    out: dict[str, Any] = {}
    if quakes:
        cut = relative_cut(quakes)
        hvs = [q["hv"] for q in quakes if q["hv"] is not None]
        out["quakes"] = {
            "n": len(quakes),
            "lf_hf_median": r3(float(np.median([q["lf_hf"] for q in quakes]))),
            "centroid_median_hz": r3(float(np.median([q["centroid_hz"] for q in quakes]))),
            "hv_median": r3(float(np.median(hvs))) if hvs else None,
            "nepal_full_share": r3(sum(q["nepal_full"] for q in quakes) / len(quakes)),
            "nepal_spectral_share": r3(sum(q["nepal_spectral"] for q in quakes) / len(quakes)),
            "relative_cut": [r3(cut[0]), r3(cut[1])],
            "relative_share": r3(loo_share(quakes)),
        }
    if event_row is not None:
        ev = {
            "lf_hf": r3(event_row["lf_hf"]),
            "centroid_hz": r3(event_row["centroid_hz"]),
            "hv": r3(event_row["hv"]),
            "nepal_full": event_row["nepal_full"],
            "nepal_spectral": event_row["nepal_spectral"],
        }
        if quakes:
            ev["relative"] = relative_pass(event_row, relative_cut(quakes))
        for k in (
            "start_after_first_trigger_s",
            "decision_after_first_trigger_s",
            "looks_past_segment_end_s",
        ):
            if k in event_row:
                ev[k] = round(float(event_row[k]), 1)
        out["event"] = ev
    return out


def summarise(rec: Record) -> dict[str, Any]:
    rules = {}
    for rule in RULES:
        quakes = [q[rule] for q in rec.quake_rules if rule in q]
        block = judged(rec.event_rules.get(rule), quakes)
        if quakes:
            looks = [q[rule]["looks_past_segment_end_s"] for q in rec.quake_rules if rule in q]
            block["quakes"]["share_looking_past_segment_end"] = r3(
                sum(x > 0 for x in looks) / len(looks)
            )
        rules[rule] = block
    sweep_rows = []
    for off in SWEEP_OFFSETS_S:
        quakes = [s[off] for s in rec.quake_sweep if off in s]
        row: dict[str, Any] = {"offset_s": off}
        row.update(judged(rec.event_sweep.get(off), quakes))
        sweep_rows.append(row)
    out: dict[str, Any] = {
        "event": rec.event,
        "distance_km": round(rec.distance_km, 1),
        "status": "ok" if rec.event_rules else "no_trigger",
        "onset_utc": rec.onset_utc,
        "quakes_usable": len(rec.quake_rules),
        "quakes_first_trigger_is_labelled_onset": rec.quakes_first_is_labelled,
        "quakes_have_hv": rec.has_quake_hv,
        "rules": rules,
        "sweep": sweep_rows,
    }
    if rec.event_sweep:
        out["sensitivity"] = sensitivity(rec.event_sweep)
    return out


def sensitivity(sw: dict[float, dict[str, Any]]) -> dict[str, Any]:
    def spread(keys: list[float], name: str) -> list[float | None]:
        vals = [sw[k][name] for k in keys if k in sw and sw[k][name] is not None]
        return [r3(min(vals)), r3(max(vals))] if vals else [None, None]

    every = sorted(sw)
    near = [k for k in every if abs(k) <= 10.0]
    after = [k for k in every if k >= 0.0]
    return {
        "lf_hf_range": spread(every, "lf_hf"),
        "centroid_range_hz": spread(every, "centroid_hz"),
        "hv_range": spread(every, "hv"),
        "lf_hf_range_within_10s": spread(near, "lf_hf"),
        "centroid_range_within_10s_hz": spread(near, "centroid_hz"),
        "lf_hf_range_after_onset": spread(after, "lf_hf"),
        "offsets_measured": len(every),
        "offsets_nepal_full_pass": [k for k in every if sw[k]["nepal_full"]],
        "offsets_nepal_spectral_pass": [k for k in every if sw[k]["nepal_spectral"]],
    }


def totals(stations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    ok = {k: v for k, v in stations.items() if v["status"] == "ok"}
    for rule in RULES:
        evs = {k: v["rules"][rule].get("event") for k, v in ok.items()}
        evs = {k: e for k, e in evs.items() if e is not None}
        pooled: dict[str, Any] = {}
        for label, prefix in (("nepal", ("NK.", "IO.")), ("bondo", ("CH.",)), ("taan", ("AK.",))):
            qs = [v["rules"][rule]["quakes"] for k, v in stations.items() if k.startswith(prefix)]
            n = sum(q["n"] for q in qs)
            pooled[label] = {
                "n": n,
                "nepal_full_share": r3(sum(q["nepal_full_share"] * q["n"] for q in qs) / n),
                "relative_share": r3(sum(q["relative_share"] * q["n"] for q in qs) / n),
            }
        out[rule] = {
            "records": len(evs),
            "nepal_full_pass": sorted(k for k, e in evs.items() if e["nepal_full"]),
            "nepal_spectral_pass": sorted(k for k, e in evs.items() if e["nepal_spectral"]),
            "relative_pass": sorted(k for k, e in evs.items() if e.get("relative")),
            "quakes": pooled,
            "event_decision_after_first_trigger_s": [
                min(e["decision_after_first_trigger_s"] for e in evs.values()),
                max(e["decision_after_first_trigger_s"] for e in evs.values()),
            ],
            "events_looking_past_segment_end": sorted(
                k for k, e in evs.items() if e["looks_past_segment_end_s"] > 0
            ),
        }
    return out


def main() -> int:
    client = CachedWaveformClient()
    records: list[Record] = []
    for key in ("NK.KKN", "IO.EVN"):
        records.append(nepal_record(client, key))
        print(f"  {key} done", flush=True)
    for mod, event, prov in (
        (BONDO, "2017 Bondo", BONDO.PROVIDER),
        (TAAN, "2015 Taan Fiord", TAAN.PROVIDER),
    ):
        oc = CachedWaveformClient(provider=prov)
        for station in mod.STATIONS:
            records.append(outside_record(oc, mod, station, event))
            print(f"  {mod.NETWORK}.{station} done", flush=True)

    stations = {r.key: summarise(r) for r in records}
    for key, s in stations.items():
        line = (
            f"{key:<9} {s['distance_km']:6.1f} km  {s['status']:<10} quakes {s['quakes_usable']:>3}"
        )
        if s["status"] == "ok":
            sens = s["sensitivity"]
            line += f"  LF/HF {sens['lf_hf_range']}  centroid {sens['centroid_range_hz']}"
        print(line)
        for rule in RULES:
            b = s["rules"][rule]
            ev = b.get("event")
            q = b.get("quakes", {})
            if ev is None:
                continue
            print(
                f"    {rule:<26} LF/HF {ev['lf_hf']:>8}  cen {ev['centroid_hz']:>6}  H/V {ev['hv']}"
                f"  nepal {ev['nepal_full']!s:<5} rel {ev.get('relative')!s:<5}"
                f"  | quakes nepal {q.get('nepal_full_share')}  rel {q.get('relative_share')}"
            )
    tot = totals(stations)
    print()
    for rule, t in tot.items():
        print(
            f"{rule:<26} nepal {len(t['nepal_full_pass'])}/{t['records']}"
            f"  relative {len(t['relative_pass'])}/{t['records']}"
            f"  quakes {t['quakes']}  decision {t['event_decision_after_first_trigger_s']} s"
        )

    summary = {
        "experiment": "exp034_onset_sensitivity",
        "segment_s": SEGMENT_S,
        "sweep_offsets_s": list(SWEEP_OFFSETS_S),
        "rules": RULE_TEXT,
        "settings": {
            "delay_s": DELAY_S,
            "peak_search_s": PEAK_SEARCH_S,
            "peak_offset_s": PEAK_OFFSET_S,
            "envelope_smoothing_s": SMOOTH_S,
            "long_segment_s": LONG_SEGMENT_S,
            "relative_quantile": QUANTILE,
            "earthquake_search": "after the origin and within "
            f"{DEFAULT_TOLERANCE_S:.0f} s of the predicted P arrival",
            "event_search_s": {
                "2026 Bhote Koshi": list(NEPAL_EVENT_SEARCH_S),
                "2017 Bondo": list(BONDO.EVENT_SEARCH_S),
                "2015 Taan Fiord": list(TAAN.EVENT_SEARCH_S),
            },
        },
        "nepal_thresholds": {
            "lf_hf_min": DEFAULT.classify.cascade_segment_lf_hf,
            "centroid_max_hz": DEFAULT.classify.cascade_segment_centroid_hz,
            "hv_min": DEFAULT.classify.segment_hv_min,
        },
        "totals": tot,
        "stations": stations,
    }
    (HERE / "results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {HERE / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
