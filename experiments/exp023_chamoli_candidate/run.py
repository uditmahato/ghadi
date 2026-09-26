"""Experiment 023: is the Chamoli 2021 rock and ice avalanche a second positive? (#6)

**Question.** The positive class is one event. The 7 February 2021 Chamoli avalanche
is a large, well recorded rock and ice failure with a published seismic origin time.
It is far from both open stations (about 580 and 730 km), so it cannot be a positive
for lead time or fusion. Can the seismic detector see it at all, and does its decision
segment have the low frequency shape the classifier was built on?

**Design.** The same steps as every event so far: the archive window around the origin
on both stations, the detector, the onset picked against the predicted arrival for the
catalogued distance, the 120 s decision segment's spectral features, and the three
component descriptors where the horizontals exist. Then the same values for the 2026
event on the same station, side by side. A wide picking tolerance is used because at
this range the first trigger may sit on any of several phases.

    python experiments/exp023_chamoli_candidate/run.py
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

from ghadi.catalog import load_catalog  # noqa: E402
from ghadi.classify import classify_segment  # noqa: E402
from ghadi.config import DEFAULT, EVEREST, KAKANI, Station, StationSite  # noqa: E402
from ghadi.detect import pick_onset, sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import extract, preprocess  # noqa: E402
from ghadi.features_3c import hv_ratio  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402

SITES: dict[str, StationSite] = {"NK.KKN": KAKANI, "IO.EVN": EVEREST}
EVENTS = {
    "IND-2021-02-07-CHAMOLI-001": (600.0, 2100.0),
    "NPL-2026-08-26-BHOTEKOSHI-001": (600.0, 2100.0),
}
PICK_TOLERANCE_S = 90.0
IO_EVN_THRESHOLDS = {"lf_hf": 15.072605742437103, "centroid_hz": 1.5325246132329207}


def load(
    client: CachedWaveformClient, site: StationSite, channel: str, start: datetime, end: datetime
) -> tuple[np.ndarray | None, float]:
    st = Station(site.site.network, site.site.station, site.site.location, channel)
    r = client.get_waveforms(
        WaveformRequest(st.network, st.station, st.location, st.channel, start, end)
    )
    if not r.ok:
        return None, 0.0
    tr = r.stream.merge(fill_value="interpolate")[0]
    return np.asarray(tr.data, dtype=float), float(tr.stats.sampling_rate)


def examine(
    client: CachedWaveformClient,
    key: str,
    site: StationSite,
    origin: datetime,
    lat: float,
    lon: float,
    pre: float,
    post: float,
) -> dict[str, Any]:
    start, end = origin - timedelta(seconds=pre), origin + timedelta(seconds=post)
    z, sr = load(client, site, site.site.channel, start, end)
    if z is None:
        return {"status": "no_waveform"}
    proc = preprocess(z, sr)
    det = sta_lta(proc, sr, preprocessed=True)
    distance = haversine_km(site.latitude, site.longitude, lat, lon)
    pick = pick_onset(
        det.triggers, origin_offset_s=pre, distance_km=distance, tolerance_s=PICK_TOLERANCE_S
    )
    rec: dict[str, Any] = {
        "status": "ok",
        "distance_km": round(distance, 1),
        "triggers": len(det.triggers),
        "max_sta_lta": round(det.max_ratio, 2),
        "pick_reason": pick.reason,
    }
    if not pick.ok or pick.onset_s is None:
        rec["status"] = "no_pick"
        return rec
    seg = extract(
        proc,
        sr,
        preprocessed=True,
        onset_s=pick.onset_s,
        segment_s=DEFAULT.seismic.decision_segment_s,
    )
    rec.update(
        {
            "onset_utc": (start + timedelta(seconds=pick.onset_s)).isoformat(),
            "seconds_after_origin": round(pick.onset_s - pre, 1),
            "signal_present": seg.signal_present,
            "lf_hf": round(seg.spectral_ratio_low_high, 4),
            "centroid_hz": round(seg.spectral_centroid_hz, 4),
            "duration_80_s": round(seg.duration_80_s, 1),
            "peak_amplitude": float(seg.peak_amplitude),
        }
    )
    if key == "NK.KKN":
        cls = classify_segment(seg.spectral_ratio_low_high, seg.spectral_centroid_hz)
        rec["mass_movement_like_at_station_thresholds"] = cls.mass_movement_like
    else:
        rec["mass_movement_like_at_station_thresholds"] = bool(
            seg.spectral_ratio_low_high >= IO_EVN_THRESHOLDS["lf_hf"]
            and seg.spectral_centroid_hz <= IO_EVN_THRESHOLDS["centroid_hz"]
        )
    n, _ = load(client, site, site.site.channel[:2] + "N", start, end)
    e, _ = load(client, site, site.site.channel[:2] + "E", start, end)
    if n is not None and e is not None:
        m = min(z.size, n.size, e.size)
        pn, pe, pz = preprocess(n[:m], sr), preprocess(e[:m], sr), preprocess(z[:m], sr)
        a = max(round(pick.onset_s * sr), 0)
        b = min(a + round(DEFAULT.seismic.decision_segment_s * sr), m)
        rec["hv_segment"] = (
            round(float(hv_ratio(pz[a:b], pn[a:b], pe[a:b])), 4) if b - a > 2 else None
        )
    else:
        rec["hv_segment"] = None
    return rec


def main() -> int:
    client = CachedWaveformClient()
    events = {e.event_id: e for e in load_catalog()}
    results: dict[str, Any] = {"experiment": "exp023_chamoli_candidate", "events": {}}
    for event_id, (pre, post) in EVENTS.items():
        ev = events[event_id]
        results["events"][event_id] = {
            "origin_utc": ev.origin_utc.isoformat(),
            "stations": {
                key: examine(client, key, site, ev.origin_utc, ev.lat, ev.lon, pre, post)
                for key, site in SITES.items()
            },
        }
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    for event_id, rec in results["events"].items():
        print(event_id)
        for key, st in rec["stations"].items():
            print(f"   {key}: {json.dumps(st)}")
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
