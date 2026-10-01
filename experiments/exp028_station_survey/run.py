"""Experiment 028: is there a third station?

**Question.** Two stations carry everything, and on 2026-10-01 one of them sent no live
data. Which open broadband stations lie within about 300 km of the 2026 source, which
of them hold archive data for the event, which of those show it, and which are
delivering live data now?

**Design.**

* **Inventory.** The FDSN station service at EarthScope for broadband vertical channels
  (BHZ, HHZ) within 300 km of the catalogued source, all networks, with their epochs.
  Synthetic networks are excluded.
* **Archive on the day.** For every station open on 26 August 2026, the 45 minute
  window around the event. A station that returns data is run through the detector and
  the same onset picker used throughout.
* **Seen or not.** The picked onset, the peak short over long average ratio, and the
  decision segment's spectral values, beside the two stations already in use.
* **Live now.** A 30 second SeedLink probe per station that had archive data, on the
  public server the shadow service uses. A probe only says what is true at the moment
  it runs, and the run time is recorded.

    python experiments/exp028_station_survey/run.py
"""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import DEFAULT, SYNTHETIC_NETWORKS, Station  # noqa: E402
from ghadi.detect import pick_onset, sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import extract, preprocess  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402
from ghadi.sources import SeedLinkSource  # noqa: E402

SOURCE = (28.255, 85.520)
ORIGIN = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)
RADIUS_KM = 300.0
PRE_S, POST_S = 600.0, 2100.0
PROBE_S = 30.0
INVENTORY = Path(__file__).resolve().parent / "inventory.json"


def inventory() -> list[dict[str, Any]]:
    """Broadband vertical channels near the source, cached so the survey can be rerun."""
    if INVENTORY.exists():
        loaded: list[dict[str, Any]] = json.loads(INVENTORY.read_text(encoding="utf-8"))
        return loaded
    from obspy import UTCDateTime
    from obspy.clients.fdsn import Client

    client = Client("EARTHSCOPE")
    inv = client.get_stations(
        latitude=SOURCE[0],
        longitude=SOURCE[1],
        maxradius=RADIUS_KM / 111.195,
        channel="BHZ,HHZ",
        level="channel",
        starttime=UTCDateTime(2014, 1, 1),
    )
    rows: list[dict[str, Any]] = []
    for net in inv:
        if net.code in SYNTHETIC_NETWORKS:
            continue
        for sta in net:
            for ch in sta:
                rows.append(
                    {
                        "network": net.code,
                        "station": sta.code,
                        "location": ch.location_code,
                        "channel": ch.code,
                        "lat": sta.latitude,
                        "lon": sta.longitude,
                        "start": str(ch.start_date)[:10] if ch.start_date else None,
                        "end": str(ch.end_date)[:10] if ch.end_date else None,
                        "sampling_rate": ch.sample_rate,
                        "restricted": (ch.restricted_status or sta.restricted_status)
                        not in (None, "open"),
                    }
                )
    INVENTORY.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def open_on(row: dict[str, Any], when: datetime) -> bool:
    start = datetime.fromisoformat(row["start"]).replace(tzinfo=UTC) if row["start"] else None
    end = datetime.fromisoformat(row["end"]).replace(tzinfo=UTC) if row["end"] else None
    return (start is None or start <= when) and (end is None or end >= when)


def examine(client: CachedWaveformClient, row: dict[str, Any]) -> dict[str, Any]:
    r = client.get_waveforms(
        WaveformRequest(
            row["network"],
            row["station"],
            row["location"],
            row["channel"],
            ORIGIN - timedelta(seconds=PRE_S),
            ORIGIN + timedelta(seconds=POST_S),
        )
    )
    if not r.ok:
        return {"archive": False, "reason": (r.error or "")[:90]}
    tr = r.stream.merge(fill_value="interpolate")[0]
    sr = float(tr.stats.sampling_rate)
    data = np.asarray(tr.data, dtype=float)
    if data.size < sr * 900:
        return {"archive": False, "reason": "window mostly missing"}
    proc = preprocess(data, sr)
    det = sta_lta(proc, sr, preprocessed=True)
    distance = haversine_km(row["lat"], row["lon"], *SOURCE)
    pick = pick_onset(det.triggers, origin_offset_s=PRE_S, distance_km=distance, tolerance_s=30.0)
    out: dict[str, Any] = {
        "archive": True,
        "triggers": len(det.triggers),
        "max_sta_lta": round(det.max_ratio, 2),
        "seen": bool(pick.ok),
    }
    if pick.ok and pick.onset_s is not None:
        seg = extract(
            proc,
            sr,
            preprocessed=True,
            onset_s=pick.onset_s,
            segment_s=DEFAULT.seismic.decision_segment_s,
        )
        out.update(
            {
                "onset_utc": (
                    ORIGIN - timedelta(seconds=PRE_S) + timedelta(seconds=pick.onset_s)
                ).isoformat(),
                "seconds_after_origin": round(pick.onset_s - PRE_S, 1),
                "lf_hf": round(float(seg.spectral_ratio_low_high), 2),
                "centroid_hz": round(float(seg.spectral_centroid_hz), 2),
            }
        )
    return out


def live_probe(row: dict[str, Any]) -> dict[str, Any]:
    station = Station(row["network"], row["station"], row["location"], row["channel"])
    source = SeedLinkSource(station=station, key=f"{row['network']}.{row['station']}")
    delays: list[float] = []

    def run() -> None:
        try:
            for p in source.packets():
                delays.append(p.delay_s)
        except Exception:
            return

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(PROBE_S)
    source.stop()
    return {
        "live_packets": len(delays),
        "live_delay_median_s": round(float(np.median(delays)), 1) if delays else None,
    }


def main() -> int:
    rows = inventory()
    client = CachedWaveformClient()
    stations: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = f"{row['network']}.{row['station']}"
        rec = stations.setdefault(
            key,
            {
                "lat": row["lat"],
                "lon": row["lon"],
                "distance_km": round(haversine_km(row["lat"], row["lon"], *SOURCE), 1),
                "channels": [],
                "restricted": row["restricted"],
            },
        )
        rec["channels"].append(
            {k: row[k] for k in ("location", "channel", "start", "end", "sampling_rate")}
        )
    candidates = []
    for row in rows:
        key = f"{row['network']}.{row['station']}"
        if open_on(row, ORIGIN) and "event" not in stations[key]:
            stations[key]["event"] = {"checked_channel": f"{row['location']}.{row['channel']}"}
            candidates.append(row)
    print(f"{len(stations)} stations within {RADIUS_KM:.0f} km; {len(candidates)} open on the day")
    for row in candidates:
        key = f"{row['network']}.{row['station']}"
        stations[key]["event"].update(examine(client, row))
        if stations[key]["event"].get("archive"):
            stations[key]["live"] = live_probe(row)
        e = stations[key]["event"]
        print(
            f"   {key:<10} {stations[key]['distance_km']:6.1f} km  archive {e.get('archive')}  "
            f"seen {e.get('seen')}  max {e.get('max_sta_lta')}  live {stations[key].get('live')}",
            flush=True,
        )
    results = {
        "experiment": "exp028_station_survey",
        "source": {"lat": SOURCE[0], "lon": SOURCE[1]},
        "radius_km": RADIUS_KM,
        "probed_utc": datetime.now(tz=UTC).isoformat(),
        "stations": dict(sorted(stations.items(), key=lambda kv: kv[1]["distance_km"])),
    }
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
