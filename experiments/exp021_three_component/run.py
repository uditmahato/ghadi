"""Experiment 021: do the three component features separate the cascade from noise? (#37)

**Question.** ``ghadi.features_3c`` computes particle motion descriptors (rectilinearity,
planarity, incidence, azimuth, horizontal to vertical ratio) and has tests, but nothing
uses it. Particle motion is the classic way to tell a local surface source from a distant
body wave arrival. Do these descriptors separate the 2026 cascade from the windows the
single station test counts as false alarms?

**Design.**

* The 2026 event on both stations: all three channels for the cached windows, the onset
  picked as in exp019, polarisation over the 20 s after the onset, and the horizontal to
  vertical ratio over the 120 s decision segment.
* Every exp018 false alarm window at its own station: the two horizontal channels are
  fetched to match the cached vertical, and the same descriptors are computed at each
  passing segment's onset.
* For each descriptor, where the 2026 value sits in the false alarm distribution, and
  how many false alarms a threshold at the 2026 value would remove. That threshold is
  fitted to n = 1, so the count is what such a rule could remove at best, not what it
  would remove in operation.

    python experiments/exp021_three_component/run.py
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

from ghadi.config import DEFAULT, EVEREST, KAKANI, Station, StationSite  # noqa: E402
from ghadi.detect import pick_onset, sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import preprocess  # noqa: E402
from ghadi.features_3c import hv_ratio, polarisation_over_window  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402

EXP018 = REPO_ROOT / "experiments" / "exp018_io_evn_false_alarm_rate" / "results.json"
SITES = {"NK.KKN": KAKANI, "IO.EVN": EVEREST}
ZONE = (28.255, 85.520)
CASCADE_ORIGIN = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)
EVENT_WINDOWS = {"NK.KKN": (600.0, 2100.0), "IO.EVN": (600.0, 1500.0)}
NOISE_WINDOW_S = 2100.0
POL_S = 20.0
DESCRIPTORS = ("rectilinearity", "planarity", "incidence_deg", "hv_ratio", "hv_ratio_segment")


def load_3c(
    client: CachedWaveformClient, site: StationSite, start: datetime, end: datetime
) -> tuple[dict[str, np.ndarray] | None, float]:
    out: dict[str, np.ndarray] = {}
    sr = 0.0
    for component in ("Z", "N", "E"):
        channel = site.site.channel[:2] + component
        station = Station(site.site.network, site.site.station, site.site.location, channel)
        result = client.get_waveforms(
            WaveformRequest(
                station.network, station.station, station.location, station.channel, start, end
            )
        )
        if not result.ok:
            return None, 0.0
        trace = result.stream.merge(fill_value="interpolate")[0]
        out[component] = np.asarray(trace.data, dtype=float)
        sr = float(trace.stats.sampling_rate)
    n = min(v.size for v in out.values())
    return {k: v[:n] for k, v in out.items()}, sr


def descriptors(comp: dict[str, np.ndarray], sr: float, onset_s: float) -> dict[str, float]:
    z = preprocess(comp["Z"], sr)
    n = preprocess(comp["N"], sr)
    e = preprocess(comp["E"], sr)
    pol = polarisation_over_window(z, n, e, sr, onset_s, duration_s=POL_S)
    start = max(round(onset_s * sr), 0)
    stop = min(start + round(DEFAULT.seismic.decision_segment_s * sr), z.size)
    seg_hv = hv_ratio(z[start:stop], n[start:stop], e[start:stop]) if stop - start > 2 else np.nan
    d = pol.as_dict()
    d["hv_ratio_segment"] = float(seg_hv)
    return {k: (None if not np.isfinite(v) else round(float(v), 4)) for k, v in d.items()}


def event_values(client: CachedWaveformClient) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, site in SITES.items():
        pre, post = EVENT_WINDOWS[key]
        start = CASCADE_ORIGIN - timedelta(seconds=pre)
        comp, sr = load_3c(client, site, start, CASCADE_ORIGIN + timedelta(seconds=post))
        if comp is None:
            out[key] = {"status": "no_3c_waveform"}
            continue
        proc = preprocess(comp["Z"], sr)
        detection = sta_lta(proc, sr, preprocessed=True)
        distance = haversine_km(site.latitude, site.longitude, *ZONE)
        pick = pick_onset(detection.triggers, origin_offset_s=pre, distance_km=distance)
        if not pick.ok or pick.onset_s is None:
            out[key] = {"status": "no_pick", "reason": pick.reason}
            continue
        out[key] = {
            "status": "ok",
            "onset_utc": (start + timedelta(seconds=pick.onset_s)).isoformat(),
            **descriptors(comp, sr, pick.onset_s),
        }
    return out


def false_alarm_values(client: CachedWaveformClient, exp018: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, rec in exp018["stations"].items():
        site = SITES[key]
        rows: list[dict[str, Any]] = []
        for fa in rec["false_alarm_windows"]:
            start = datetime.fromisoformat(fa["window_start_utc"])
            comp, sr = load_3c(client, site, start, start + timedelta(seconds=NOISE_WINDOW_S))
            if comp is None:
                rows.append({"window_start_utc": fa["window_start_utc"], "status": "no_3c"})
                continue
            for seg in fa["passing_segments"]:
                rows.append(
                    {
                        "window_start_utc": fa["window_start_utc"],
                        "status": "ok",
                        "on_s": seg["on_s"],
                        **descriptors(comp, sr, seg["on_s"]),
                    }
                )
        out[key] = rows
    return out


def compare(event: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r["status"] == "ok"]
    windows = {r["window_start_utc"] for r in ok}
    summary: dict[str, Any] = {"segments": len(ok), "windows": len(windows)}
    for name in DESCRIPTORS:
        values = np.array([r[name] for r in ok if r.get(name) is not None], dtype=float)
        ev = event.get(name)
        if values.size == 0 or ev is None:
            summary[name] = {"status": "no_data"}
            continue
        # Which direction separates: the cascade is a shallow surface source, so higher
        # horizontal energy and higher incidence are the expected side. Report both.
        above = int(np.count_nonzero(values >= ev))
        below = int(np.count_nonzero(values <= ev))
        # Windows removed if the rule kept only segments on the cascade's side.
        per_window_max = {}
        per_window_min = {}
        for r in ok:
            v = r.get(name)
            if v is None:
                continue
            w = r["window_start_utc"]
            per_window_max[w] = max(per_window_max.get(w, -np.inf), v)
            per_window_min[w] = min(per_window_min.get(w, np.inf), v)
        summary[name] = {
            "event": ev,
            "noise_median": round(float(np.median(values)), 4),
            "noise_p10": round(float(np.percentile(values, 10)), 4),
            "noise_p90": round(float(np.percentile(values, 90)), 4),
            "segments_at_or_above_event": above,
            "segments_at_or_below_event": below,
            "windows_removed_if_must_be_at_least_event": sum(
                1 for v in per_window_max.values() if v < ev
            ),
            "windows_removed_if_must_be_at_most_event": sum(
                1 for v in per_window_min.values() if v > ev
            ),
        }
    return summary


def main() -> int:
    client = CachedWaveformClient()
    exp018 = json.loads(EXP018.read_text(encoding="utf-8"))
    event = event_values(client)
    noise = false_alarm_values(client, exp018)
    results: dict[str, Any] = {
        "experiment": "exp021_three_component",
        "polarisation_window_s": POL_S,
        "event_2026": event,
        "false_alarm_segments": noise,
        "comparison": {key: compare(event.get(key, {}), noise.get(key, [])) for key in SITES},
    }
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    for key in SITES:
        print(f"{key} 2026: {event.get(key)}")
        comp = results["comparison"][key]
        print(f"{key} false alarm segments {comp['segments']} in {comp['windows']} windows")
        for name in DESCRIPTORS:
            print(f"   {name}: {comp.get(name)}")
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
