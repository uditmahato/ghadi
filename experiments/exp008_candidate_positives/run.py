"""Experiment 008 — can the positive class grow beyond n = 1?

**The problem.** Five catalogue events have waveform data (exp007) but no labelled
window, because their origin times come from news reports with uncertainties of minutes
to hours. Somewhere inside each uncertainty window there may be a signal. Finding it
would take the positive class from 1 toward 6 and make M3 a supervised problem at all.

**The trap, and the design that avoids it.** Using the mass-movement spectral criteria
to *find* positives and then evaluating those criteria on what they found is circular:
it would manufacture a corpus that agrees with the detector by construction, and every
subsequent separation number would be meaningless.

So selection and corroboration are kept strictly apart:

- **Selection is class-agnostic.** Candidates come from STA/LTA, which knows nothing
  about mass movements, restricted to the reported uncertainty window.
- **Corroboration is independent of the features.** A candidate is strengthened by
  *cross-station timing consistency* — the same arrival seen at two stations within the
  travel-time difference a common source would produce — and by *not* being explained by
  a catalogued earthquake, local or teleseismic.
- **Spectral features are read out last, and never used to select.** They are reported
  so a human can judge, and so that a candidate which looks nothing like a mass movement
  is visible as such rather than quietly dropped.

**Nothing here produces a label.** Output is a ranked candidate list for human
adjudication against the published accounts of each event. A candidate that survives
this is a hypothesis worth checking, not a positive.

    python experiments/exp008_candidate_positives/run.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.catalog import load_catalog  # noqa: E402
from ghadi.detect import sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import preprocess  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402
from ghadi.teleseism import Origin, explain  # noqa: E402

HERE = Path(__file__).parent
GLOBAL_CATALOGUE = REPO_ROOT / "data" / "corpus" / "global_catalogue.json"

# Stations to search, with coordinates for the cross-station timing check.
STATIONS: tuple[tuple[str, str, str, str, float, float], ...] = (
    ("IO", "EVN", "", "BHZ", 27.9592, 86.8133),
    ("NK", "KKN", "", "BHZ", 27.8000, 85.2790),
)

# The 2026 cascade already has a labelled window; it is the reference, not a candidate.
EXCLUDE_EVENT_IDS = {"NPL-2026-08-26-BHOTEKOSHI-001"}

# Chunk the search window so one bad hour does not lose the whole event.
CHUNK_S = 3600.0
MARGIN_S = 900.0  # searched either side of the stated uncertainty
# A common source produces a *specific* lag between two stations, set by the difference
# in their distances to it. Requiring only that the lag be small is far too weak: it
# accepts a pair whose nearer station fires later, which no single source can produce.
# The lag must match the predicted one, in sign and size.
LAG_TOLERANCE_S = 25.0
# Widest plausible apparent velocity range for the lag prediction (km/s).
FAST_KM_S = 6.0
SLOW_KM_S = 3.0
MIN_PEAK_RATIO = 6.0  # ignore marginal triggers; the baseline fires constantly


@dataclass
class Candidate:
    station: str
    time_utc: datetime
    peak_ratio: float
    duration_s: float


def search_station(
    net: str,
    sta: str,
    loc: str,
    cha: str,
    start: datetime,
    end: datetime,
    client: CachedWaveformClient,
) -> tuple[list[Candidate], dict[str, Any]]:
    """Run the class-agnostic detector across the search window, in chunks."""
    candidates: list[Candidate] = []
    chunks_ok = chunks_failed = 0
    cursor = start

    while cursor < end:
        chunk_end = min(cursor + timedelta(seconds=CHUNK_S), end)
        result = client.get_waveforms(WaveformRequest(net, sta, loc, cha, cursor, chunk_end))
        if not result.ok:
            chunks_failed += 1
            cursor = chunk_end
            continue
        try:
            trace = result.stream.merge(fill_value="interpolate")[0]
            sr = float(trace.stats.sampling_rate)
            proc = preprocess(np.asarray(trace.data, dtype=float), sr)
            detection = sta_lta(proc, sr, preprocessed=True)
        except Exception:
            chunks_failed += 1
            cursor = chunk_end
            continue

        chunks_ok += 1
        for trigger in detection.triggers:
            if trigger.peak_ratio < MIN_PEAK_RATIO:
                continue
            candidates.append(
                Candidate(
                    station=f"{net}.{sta}",
                    time_utc=cursor + timedelta(seconds=trigger.on_s),
                    peak_ratio=trigger.peak_ratio,
                    duration_s=trigger.off_s - trigger.on_s,
                )
            )
        cursor = chunk_end

    return candidates, {"chunks_ok": chunks_ok, "chunks_failed": chunks_failed}


def main() -> int:
    origins = []
    if GLOBAL_CATALOGUE.exists():
        data = json.loads(GLOBAL_CATALOGUE.read_text(encoding="utf-8"))
        origins = [
            Origin(
                time_utc=datetime.fromisoformat(o["time_utc"]),
                latitude=o["latitude"],
                longitude=o["longitude"],
                magnitude=o["magnitude"],
                place=o.get("place", ""),
            )
            for o in data["origins"]
        ]

    client = CachedWaveformClient()
    events = [e for e in load_catalog() if e.event_id not in EXCLUDE_EVENT_IDS]
    report: list[dict[str, Any]] = []

    for event in events:
        half = event.origin_uncertainty_s + MARGIN_S
        start = event.origin_utc - timedelta(seconds=half)
        end = event.origin_utc + timedelta(seconds=half)
        span_h = (end - start).total_seconds() / 3600.0

        print(f"\n=== {event.event_id} ===")
        print(
            f"  origin {event.origin_utc.isoformat()} +/- {event.origin_uncertainty_s:.0f}s "
            f"({event.time_source}); searching {span_h:.1f} h"
        )

        per_station: dict[str, list[Candidate]] = {}
        fetch_stats: dict[str, Any] = {}
        for net, sta, loc, cha, lat, lon in STATIONS:
            distance = haversine_km(lat, lon, event.lat, event.lon)
            found, stats = search_station(net, sta, loc, cha, start, end, client)
            key = f"{net}.{sta}"
            per_station[key] = found
            fetch_stats[key] = {**stats, "distance_km": round(distance, 1)}
            print(
                f"  {key:<8} {distance:>6.0f} km  chunks {stats['chunks_ok']} ok / "
                f"{stats['chunks_failed']} missing  triggers>={MIN_PEAK_RATIO}: {len(found)}"
            )

        # Cross-station agreement: the corroboration that does not touch the features.
        # The lag between stations must match what the event location predicts —
        # in sign as well as size. The nearer station must fire first.
        keys = [k for k, v in per_station.items() if v]
        agreed: list[dict[str, Any]] = []
        if len(keys) >= 2:
            dist = {
                f"{net}.{sta}": haversine_km(lat, lon, event.lat, event.lon)
                for net, sta, _loc, _cha, lat, lon in STATIONS
            }
            a, b = per_station[keys[0]], per_station[keys[1]]
            # Predicted lag of b relative to a, from the distance difference.
            gap_km = dist[keys[1]] - dist[keys[0]]
            lag_fast, lag_slow = gap_km / FAST_KM_S, gap_km / SLOW_KM_S
            lag_lo, lag_hi = sorted((lag_fast, lag_slow))
            seen: set[str] = set()
            for ca in a:
                for cb in b:
                    signed = (cb.time_utc - ca.time_utc).total_seconds()
                    if not (lag_lo - LAG_TOLERANCE_S <= signed <= lag_hi + LAG_TOLERANCE_S):
                        continue
                    stamp = min(ca.time_utc, cb.time_utc).isoformat()
                    if stamp in seen:  # one arrival, matched twice, is one candidate
                        continue
                    seen.add(stamp)
                    agreed.append(
                        {
                            "time_utc": stamp,
                            "observed_lag_s": round(signed, 1),
                            "predicted_lag_s": [round(lag_lo, 1), round(lag_hi, 1)],
                            "peak_ratios": [round(ca.peak_ratio, 1), round(cb.peak_ratio, 1)],
                            "stations": [ca.station, cb.station],
                        }
                    )

        # Teleseism exclusion, applied to every cross-station agreement.
        surviving = []
        for match in agreed:
            verdict = explain(
                datetime.fromisoformat(match["time_utc"]),
                origins,
                STATIONS[0][4],
                STATIONS[0][5],
            )
            match["teleseism"] = verdict.reason if verdict.suppressed else None
            if not verdict.suppressed:
                surviving.append(match)

        # How many agreements would two independent trigger streams produce by pure
        # chance? Na * Nb * 2*tolerance / span. Without this number, "4 agreements"
        # reads as evidence when it may be nothing at all.
        n_a = len(per_station.get(keys[0], [])) if keys else 0
        n_b = len(per_station.get(keys[1], [])) if len(keys) >= 2 else 0
        span_s = (end - start).total_seconds()
        # Chance rate uses the *width of the accepted lag band*, which is what a random
        # pair actually has to land in.
        band_s = (
            2 * LAG_TOLERANCE_S
            + abs(
                (dist[keys[1]] - dist[keys[0]]) / SLOW_KM_S
                - (dist[keys[1]] - dist[keys[0]]) / FAST_KM_S
            )
            if len(keys) >= 2
            else 0.0
        )
        expected_by_chance = n_a * n_b * band_s / span_s if span_s > 0 else float("nan")
        print(
            f"  cross-station agreements: {len(agreed)}  "
            f"(after teleseism exclusion: {len(surviving)})  "
            f"expected by chance: {expected_by_chance:.1f}"
        )
        for match in surviving[:5]:
            offset = (datetime.fromisoformat(match["time_utc"]) - event.origin_utc).total_seconds()
            print(
                f"    CANDIDATE {match['time_utc'][:19]}Z  "
                f"{offset:+.0f}s from reported origin  lag {match['observed_lag_s']}s "
                f"(predicted {match['predicted_lag_s']})  peaks {match['peak_ratios']}"
            )

        report.append(
            {
                "event_id": event.event_id,
                "origin_utc": event.origin_utc.isoformat(),
                "origin_uncertainty_s": event.origin_uncertainty_s,
                "time_source": event.time_source,
                "search_hours": span_h,
                "stations": fetch_stats,
                "triggers_per_station": {k: len(v) for k, v in per_station.items()},
                "cross_station_agreements": len(agreed),
                "expected_by_chance": expected_by_chance,
                "excess_over_chance": len(agreed) - expected_by_chance,
                "surviving_candidates": surviving,
            }
        )

    (HERE / "results.json").write_text(
        json.dumps(
            {
                "experiment": "exp008_candidate_positives",
                "method": (
                    "selection by class-agnostic STA/LTA inside the reported uncertainty "
                    "window; corroboration by cross-station timing agreement and "
                    "teleseism exclusion; spectral features never used to select"
                ),
                "min_peak_ratio": MIN_PEAK_RATIO,
                "lag_tolerance_s": LAG_TOLERANCE_S,
                "events": report,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {HERE / 'results.json'}")
    print(
        "\nThese are candidates for human adjudication against the published account of\n"
        "each event, not labels. Nothing here has produced a positive."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
