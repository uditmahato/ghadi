"""Experiment 020: what would the system have said, and when, for each catalogue event? (#33)

**Question.** Milestone M5 in the handoff. For every event in ``data/catalog``, push the
archive waveform through the real time path exactly as a live feed would have delivered
it, and record what the system would have produced: whether it triggered, the tier, the
score, the decision time, and for the 2026 event the lead time at each settlement.

**Design.**

* The live path (``ghadi.live``), not a separate analysis: the same overlapping windows,
  detector, decision segment, classifier, teleseism check, and fusion the shadow service
  runs. Packets are cut from the cached archive with a 6 s feed delay, the median that
  the latency run measured.
* Both stations, each with its own operating point: NK.KKN at the default thresholds,
  IO.EVN at exp010's. A station is skipped, and said to be skipped, where its archive
  has no data for the event.
* The search window is the catalogued origin plus and minus its uncertainty and
  15 minutes, as exp008 used, so an event with a news derived time is looked for
  everywhere it could be.
* No gauge, because no gauge data exists for any event. The best any station can reach
  is ADVISORY, and the write up says so.
* Only data before the moment being decided is used, because the loop cannot see
  anything else.

    python experiments/exp020_catalogue_replay/run.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.catalog import load_catalog  # noqa: E402
from ghadi.config import DEFAULT, EVEREST, KAKANI, ClassifyConfig, StationSite  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.live import FeedStats, LiveConfig, WindowVerdict, run_shadow  # noqa: E402
from ghadi.sources import ReplaySource, packets_from_trace  # noqa: E402
from ghadi.teleseism import Origin  # noqa: E402

REACH = "TRISHULI-R07"
FEED_DELAY_S = 6.0
EXTRA_SEARCH_S = 15 * 60.0
SITES: dict[str, StationSite] = {"NK.KKN": KAKANI, "IO.EVN": EVEREST}
CLASSIFY: dict[str, ClassifyConfig] = {
    "NK.KKN": DEFAULT.classify,
    "IO.EVN": replace(
        DEFAULT.classify,
        cascade_segment_lf_hf=15.072605742437103,
        cascade_segment_centroid_hz=1.5325246132329207,
    ),
}
GLOBAL_CATALOGUE = REPO_ROOT / "data" / "corpus" / "global_catalogue.json"


def load_origins() -> tuple[Origin, ...]:
    """The global M5.5+ catalogue the teleseism check uses, if it is present."""
    if not GLOBAL_CATALOGUE.exists():
        return ()
    raw = json.loads(GLOBAL_CATALOGUE.read_text(encoding="utf-8"))
    rows = raw.get("origins", raw) if isinstance(raw, dict) else raw
    out = []
    for r in rows:
        try:
            out.append(
                Origin(
                    time_utc=datetime.fromisoformat(str(r["time_utc"]).replace("Z", "+00:00")),
                    latitude=float(r["latitude"]),
                    longitude=float(r["longitude"]),
                    magnitude=float(r["magnitude"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(out)


def replay_station(
    client: CachedWaveformClient,
    site: StationSite,
    key: str,
    start: datetime,
    end: datetime,
    origins: tuple[Origin, ...],
) -> dict[str, Any]:
    if start < site.archive_start:
        return {"status": "before_archive", "archive_start": site.archive_start.isoformat()}
    result = client.get_waveforms(
        WaveformRequest(
            site.site.network, site.site.station, site.site.location, site.site.channel, start, end
        )
    )
    if not result.ok:
        return {"status": "no_waveform", "reason": result.error}
    trace = result.stream.merge(fill_value="interpolate")[0]
    sr = float(trace.stats.sampling_rate)
    first = trace.stats.starttime.datetime.replace(tzinfo=UTC)
    packets = packets_from_trace(
        np.asarray(trace.data, dtype=float), sr, first, station=key, delay_s=FEED_DELAY_S
    )
    verdicts: list[WindowVerdict] = []
    stats = FeedStats()
    cfg = replace(DEFAULT, classify=CLASSIFY[key])
    outcomes = run_shadow(
        ReplaySource(packets),
        reach=REACH,
        model_version="exp020",
        live=LiveConfig(station=key, sampling_rate=sr),
        config=cfg,
        stats=stats,
        on_verdict=verdicts.append,
        origins=origins,
        station_lat=site.latitude,
        station_lon=site.longitude,
    )
    decisions = []
    for o in outcomes:
        decisions.append(
            {
                "detected_utc": o.audit.payload["detected_utc"],
                "tier": o.decision.tier.value,
                "probability": round(o.decision.probability, 3),
                "mass_movement_like": o.audit.payload["seismic"]["mass_movement_like"],
                "suppressed": o.suppression.suppressed,
                "suppression_reason": o.suppression.reason if o.suppression.suppressed else None,
                "lead_times_min": o.lead_times_min,
            }
        )
    return {
        "status": "ok",
        "sampling_rate": sr,
        "feed": stats.as_dict(),
        "windows_by_reason": {
            r: sum(1 for v in verdicts if v.reason == r)
            for r in sorted({v.reason for v in verdicts})
        },
        "decisions": decisions,
    }


def main() -> int:
    client = CachedWaveformClient()
    origins = load_origins()
    events = load_catalog()
    results: dict[str, Any] = {
        "experiment": "exp020_catalogue_replay",
        "feed_delay_s": FEED_DELAY_S,
        "global_origins": len(origins),
        "events": [],
    }
    for event in events:
        pad = event.origin_uncertainty_s + EXTRA_SEARCH_S
        start = event.origin_utc - timedelta(seconds=pad)
        end = event.origin_utc + timedelta(seconds=pad)
        rec: dict[str, Any] = {
            "event_id": event.event_id,
            "origin_utc": event.origin_utc.isoformat(),
            "origin_uncertainty_s": event.origin_uncertainty_s,
            "time_source": event.time_source,
            "search_start_utc": start.isoformat(),
            "search_end_utc": end.isoformat(),
            "stations": {},
        }
        for key, site in SITES.items():
            rec["stations"][key] = replay_station(client, site, key, start, end, origins)
        results["events"].append(rec)
        print(f"{event.event_id}  ({event.time_source}, +/- {pad / 60:.0f} min)")
        for key, st in rec["stations"].items():
            if st["status"] != "ok":
                print(f"   {key}: {st['status']} {st.get('reason', st.get('archive_start', ''))}")
                continue
            print(f"   {key}: windows {st['windows_by_reason']}")
            for d in st["decisions"]:
                like = "like" if d["mass_movement_like"] else "not like"
                sup = f" suppressed: {d['suppression_reason']}" if d["suppressed"] else ""
                lead = f" lead {d['lead_times_min']}" if d["lead_times_min"] else ""
                print(
                    f"      {d['detected_utc']} {d['tier']:<8} p={d['probability']:.2f} "
                    f"{like}{sup}{lead}"
                )
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
