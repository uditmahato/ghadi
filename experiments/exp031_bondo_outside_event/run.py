"""Experiment 031: does the detector see a mass movement outside Nepal?

The positive class in Nepal is one event, and the thresholds were set on it. A fair
question from any reviewer: is the low frequency signature a property of this kind of
source, or of one event seen by two stations? A well recorded cascade elsewhere cannot
add a second Nepal positive, but it can answer that.

On 23 August 2017 about three million cubic metres of rock fell from the east face of
Piz Cengalo, Switzerland, at about 07:30 UTC, and turned into debris flows that reached
Bondo. The Swiss network recorded it. Two of its stations sit at almost the same
distances as the Nepal pair: CH.DAVOX at 58 km (NK.KKN is at 56) and CH.MMK at 128 km
(IO.EVN is at 131).

For each station this does what exp010 did on IO.EVN: the 120 s decision segment from
the picked onset, for the rock avalanche and for the local earthquakes on the same
station, and how many earthquakes sit at least as far into the low frequency tail as
the avalanche does. It also runs the Nepal rule unchanged (NK.KKN thresholds, default
margin, the H/V rule), which was never set for these stations: a pass or a fail there
says how well the rule travels, not whether the source is a mass movement.

The Swiss catalogue and every waveform are cached; a second run is offline.

    python experiments/exp031_bondo_outside_event/run.py
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
from ghadi.config import DEFAULT, is_offline  # noqa: E402
from ghadi.detect import pick_onset, sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import extract, preprocess  # noqa: E402
from ghadi.features_3c import hv_ratio  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402

HERE = Path(__file__).resolve().parent
PROVIDER = "ETH"

# Piz Cengalo east face. The time is the reported one; the onset is picked per station.
SOURCE_LAT, SOURCE_LON = 46.2955, 9.5875
EVENT_UTC = datetime(2017, 8, 23, 7, 30, tzinfo=UTC)
# Where the avalanche's onset may sit relative to the reported time, at any station.
EVENT_SEARCH_S = (-120.0, 240.0)

# Nearest, the two matched to the Nepal pair, one more at each distance.
STATIONS: dict[str, tuple[float, float]] = {
    "VDL": (46.483, 9.450),
    "DAVOX": (46.781, 9.880),
    "MUGIO": (45.922, 9.042),
    "MMK": (46.051, 7.964),
    "SGT05": (47.442, 9.456),
}
NETWORK = "CH"

PRE_S, POST_S = 300.0, 480.0  # the LTA needs time to settle before the onset
SEGMENT_S = DEFAULT.seismic.decision_segment_s

# Local earthquakes for the comparison population, same years and same ground.
CATALOGUE_START = datetime(2014, 1, 1, tzinfo=UTC)
CATALOGUE_END = datetime(2022, 1, 1, tzinfo=UTC)
CATALOGUE_RADIUS_DEG = 1.4
MIN_MAGNITUDE = 2.5
N_EARTHQUAKES = 50


def catalogue() -> list[dict[str, Any]]:
    path = HERE / "catalogue.json"
    if path.exists():
        return list(json.loads(path.read_text(encoding="utf-8")))
    if is_offline():
        raise SystemExit("offline and no cached catalogue")
    from obspy import UTCDateTime
    from obspy.clients.fdsn import Client

    cat = Client(PROVIDER, timeout=180).get_events(
        starttime=UTCDateTime(CATALOGUE_START),
        endtime=UTCDateTime(CATALOGUE_END),
        latitude=SOURCE_LAT,
        longitude=SOURCE_LON,
        maxradius=CATALOGUE_RADIUS_DEG,
        minmagnitude=MIN_MAGNITUDE,
    )
    rows = []
    for ev in cat:
        kind = str(ev.event_type or "earthquake")
        if kind not in ("earthquake", "None"):
            continue  # the Bondo sequence and quarry blasts are typed apart
        o = ev.preferred_origin() or ev.origins[0]
        m = ev.preferred_magnitude() or ev.magnitudes[0]
        rows.append(
            {
                "origin_utc": o.time.datetime.replace(tzinfo=UTC).isoformat(),
                "lat": float(o.latitude),
                "lon": float(o.longitude),
                "depth_km": float(o.depth or 0.0) / 1000.0,
                "magnitude": float(m.mag),
                "magnitude_type": str(m.magnitude_type or ""),
                "event_type": kind,
            }
        )
    # The largest, so most of them stand clear of the noise at 130 km too.
    rows.sort(key=lambda r: -r["magnitude"])
    rows = rows[:N_EARTHQUAKES]
    path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def load(
    client: CachedWaveformClient, station: str, start: datetime, end: datetime
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None, float] | None:
    """Vertical and two horizontals, trimmed to a common span."""
    r = client.get_waveforms(WaveformRequest(NETWORK, station, "", "HH?", start, end))
    if not r.ok:
        return None
    st = r.stream.merge(fill_value="interpolate")
    by_comp = {tr.stats.channel[-1]: tr for tr in st}
    z = by_comp.get("Z")
    if z is None:
        return None
    horiz = [by_comp.get(c) for c in ("N", "E")]
    if None in horiz:
        horiz = [by_comp.get(c) for c in ("1", "2")]
    traces = [z] + [h for h in horiz if h is not None]
    # The server returns whole records, which begin and end a little outside the
    # request. Cut every component to the request first, then to their common span.
    from obspy import UTCDateTime

    for tr in traces:
        tr.trim(UTCDateTime(start), UTCDateTime(end))
    t0 = max(tr.stats.starttime for tr in traces)
    t1 = min(tr.stats.endtime for tr in traces)
    for tr in traces:
        tr.trim(t0, t1)
    sr = float(z.stats.sampling_rate)
    # Onsets are measured from the requested start, so the data must begin there.
    if (t0.datetime.replace(tzinfo=UTC) - start).total_seconds() > 1.0:
        return None  # a late start would shift every onset; refuse rather than guess
    m = min(tr.stats.npts for tr in traces)
    if m < sr * (PRE_S + SEGMENT_S):
        return None
    zz = np.asarray(z.data[:m], dtype=float)
    hs = [np.asarray(h.data[:m], dtype=float) if h is not None else None for h in horiz]
    return zz, hs[0], hs[1], sr


def measure(
    data: tuple[np.ndarray, np.ndarray | None, np.ndarray | None, float], onset_s: float
) -> dict[str, Any] | None:
    z, n, e, sr = data
    proc = preprocess(z, sr)
    try:
        seg = extract(proc, sr, preprocessed=True, onset_s=onset_s, segment_s=SEGMENT_S)
    except ValueError:
        return None
    hv = None
    if n is not None and e is not None:
        a = max(round(onset_s * sr), 0)
        b = min(a + round(SEGMENT_S * sr), proc.size)
        v = hv_ratio(proc[a:b], preprocess(n, sr)[a:b], preprocess(e, sr)[a:b])
        hv = float(v) if np.isfinite(v) else None
    lf, cen = float(seg.spectral_ratio_low_high), float(seg.spectral_centroid_hz)
    if not (np.isfinite(lf) and np.isfinite(cen)):
        return None
    cls = classify_segment(lf, cen, segment_hv=hv)
    return {
        "lf_hf": round(lf, 3),
        "centroid_hz": round(cen, 3),
        "hv": None if hv is None else round(hv, 3),
        "duration_80_s": round(float(seg.duration_80_s), 1),
        "signal_present": bool(seg.signal_present),
        "nepal_rule_spectral": bool(
            lf >= DEFAULT.classify.cascade_segment_lf_hf
            and cen <= DEFAULT.classify.cascade_segment_centroid_hz
        ),
        "nepal_rule_full": bool(cls.mass_movement_like),
    }


def the_avalanche(client: CachedWaveformClient, station: str) -> dict[str, Any]:
    start = EVENT_UTC - timedelta(seconds=PRE_S)
    data = load(client, station, start, EVENT_UTC + timedelta(seconds=POST_S))
    if data is None:
        return {"status": "no_data"}
    det = sta_lta(preprocess(data[0], data[3]), data[3], preprocessed=True)
    near = [t for t in det.triggers if EVENT_SEARCH_S[0] <= t.on_s - PRE_S <= EVENT_SEARCH_S[1]]
    if not near:
        return {"status": "no_trigger", "max_sta_lta": round(det.max_ratio, 1)}
    trig = max(near, key=lambda t: t.peak_ratio)
    feats = measure(data, trig.on_s)
    if feats is None:
        return {"status": "segment_too_short"}
    onset = start + timedelta(seconds=trig.on_s)
    return {
        "status": "ok",
        "onset_utc": onset.isoformat(),
        "peak_sta_lta": round(trig.peak_ratio, 1),
        **feats,
    }


def an_earthquake(
    client: CachedWaveformClient, station: str, quake: dict[str, Any]
) -> dict[str, Any] | None:
    origin = datetime.fromisoformat(quake["origin_utc"])
    start = origin - timedelta(seconds=PRE_S)
    data = load(client, station, start, origin + timedelta(seconds=POST_S))
    if data is None:
        return None
    lat, lon = STATIONS[station]
    dist = haversine_km(lat, lon, quake["lat"], quake["lon"])
    det = sta_lta(preprocess(data[0], data[3]), data[3], preprocessed=True)
    pick = pick_onset(det.triggers, origin_offset_s=PRE_S, distance_km=dist)
    if not pick.ok or pick.onset_s is None:
        return None
    feats = measure(data, pick.onset_s)
    if feats is None:
        return None
    return {"magnitude": quake["magnitude"], "distance_km": round(dist, 1), **feats}


def compare(
    event: dict[str, Any], quakes: list[dict[str, Any]], event_distance_km: float
) -> dict[str, Any]:
    lf = np.array([q["lf_hf"] for q in quakes])
    cen = np.array([q["centroid_hz"] for q in quakes])
    both = (lf >= event["lf_hf"]) & (cen <= event["centroid_hz"])
    out: dict[str, Any] = {
        "n": len(quakes),
        "lf_hf_median": round(float(np.median(lf)), 3),
        "centroid_median_hz": round(float(np.median(cen)), 3),
        "at_or_above_event_lf_hf": int((lf >= event["lf_hf"]).sum()),
        "at_or_below_event_centroid": int((cen <= event["centroid_hz"]).sum()),
        "meeting_both": int(both.sum()),
        "nepal_rule_spectral_pass": int(sum(q["nepal_rule_spectral"] for q in quakes)),
        "nepal_rule_full_pass": int(sum(q["nepal_rule_full"] for q in quakes)),
    }
    # The features change with distance (exp003). Earthquakes at half to one and a half
    # times the avalanche's distance from this station are the fairer comparison.
    dist = np.array([q["distance_km"] for q in quakes])
    near = (dist >= 0.5 * event_distance_km) & (dist <= 1.5 * event_distance_km)
    out["distance_matched_n"] = int(near.sum())
    out["distance_matched_meeting_both"] = int((both & near).sum())
    hvs = [q["hv"] for q in quakes if q["hv"] is not None]
    if event.get("hv") is not None and hvs:
        out["hv_median"] = round(float(np.median(hvs)), 3)
        out["at_or_above_event_hv"] = int(sum(h >= event["hv"] for h in hvs))
    return out


def main() -> int:
    client = CachedWaveformClient(provider=PROVIDER)
    quakes = catalogue()
    print(f"{len(quakes)} catalogued earthquakes, M{quakes[-1]['magnitude']:.1f} and up")
    results: dict[str, Any] = {}
    for station, (lat, lon) in STATIONS.items():
        dist = haversine_km(lat, lon, SOURCE_LAT, SOURCE_LON)
        event = the_avalanche(client, station)
        rows = [q for q in (an_earthquake(client, station, eq) for eq in quakes) if q]
        entry: dict[str, Any] = {
            "distance_km": round(dist, 1),
            "avalanche": event,
            "earthquakes_usable": len(rows),
        }
        if event["status"] == "ok" and rows:
            entry["comparison"] = compare(event, rows, dist)
        entry["earthquakes"] = rows
        results[station] = entry
        line = f"  CH.{station:<6} {dist:6.1f} km  {event['status']}"
        if event["status"] == "ok":
            line += (
                f"  LF/HF {event['lf_hf']:.2f}  centroid {event['centroid_hz']:.2f} Hz"
                f"  H/V {event['hv']}  rule {event['nepal_rule_full']}"
            )
        if "comparison" in entry:
            c = entry["comparison"]
            line += f"  | quakes {c['n']}, both {c['meeting_both']}"
        print(line, flush=True)

    summary = {
        "experiment": "exp031_bondo_outside_event",
        "event": {
            "name": "Piz Cengalo rock avalanche, Bondo",
            "reported_utc": EVENT_UTC.isoformat(),
            "lat": SOURCE_LAT,
            "lon": SOURCE_LON,
        },
        "provider": PROVIDER,
        "segment_s": SEGMENT_S,
        "nepal_thresholds": {
            "lf_hf_min": DEFAULT.classify.cascade_segment_lf_hf,
            "centroid_max_hz": DEFAULT.classify.cascade_segment_centroid_hz,
            "hv_min": DEFAULT.classify.segment_hv_min,
        },
        "catalogue": {
            "provider": PROVIDER,
            "start": CATALOGUE_START.isoformat(),
            "end": CATALOGUE_END.isoformat(),
            "radius_deg": CATALOGUE_RADIUS_DEG,
            "min_magnitude": MIN_MAGNITUDE,
            "n": len(quakes),
        },
        "stations": results,
    }
    (HERE / "results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {HERE / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
