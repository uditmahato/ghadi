"""Experiment 019: does requiring two stations to agree cut the false alarm rate? (#31)

**Question.** exp018 measured the single station spectral test at about 14 false alarms
per station month at NK.KKN and 89 at IO.EVN. A slope failure big enough to matter is
seen at both stations, and the two arrival times constrain where it was. What happens
to the false alarm rate if a detection at one station must be matched by a trigger at
the other station at a time consistent with some source in the region, and what happens
if the source must also be consistent with the 2026 zone?

**Design.**

1. **The 2026 event.** Onsets are picked on both stations from the cached windows with
   the same picker the earlier experiments used, and ``ghadi.associate`` asks whether
   the pair is consistent with the catalogued zone, and how much of the search region
   the pair would have accepted.
2. **The false alarms.** For every window exp018 counted as a false alarm, the *other*
   station's waveform for the same window is fetched and run through the detector.
   Each passing segment's onset gives a bracket of times at which the other station
   must have triggered for the two to be one source anywhere in the region. A window
   survives if any trigger falls in that bracket. A stricter rule also requires the
   matched trigger's own segment to pass the other station's spectral thresholds.
3. **Rates.** Survivors are counted per station month on exp018's basis, with exact
   Poisson intervals.

exp008 searched the older catalogue events for cross station agreement by hand. This
experiment puts that logic in the library and measures its cost on noise.

    python experiments/exp019_two_station_association/run.py
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

from ghadi.associate import Pick, SearchRegion, arrival_bracket, associate  # noqa: E402
from ghadi.config import DEFAULT, EVEREST, KAKANI, StationSite  # noqa: E402
from ghadi.detect import pick_onset, sta_lta  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import extract, preprocess  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402

EXP018 = REPO_ROOT / "experiments" / "exp018_io_evn_false_alarm_rate" / "results.json"
ZONE = (28.255, 85.520, 8.0)
REGION = SearchRegion(27.4, 29.0, 84.6, 86.6, step_km=4.0)
SITES = {"NK.KKN": KAKANI, "IO.EVN": EVEREST}
OTHER = {"NK.KKN": "IO.EVN", "IO.EVN": "NK.KKN"}
THRESHOLDS = {
    "NK.KKN": {"lf_hf_min": 4.9188, "centroid_hz_max": 1.8852},
    "IO.EVN": {"lf_hf_min": 15.0726, "centroid_hz_max": 1.5325},
}
CASCADE_ORIGIN = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)
EVENT_WINDOWS = {  # the cached windows earlier experiments fetched
    "NK.KKN": (600.0, 2100.0),
    "IO.EVN": (600.0, 1500.0),
}
NOISE_WINDOW_S = 2100.0
HOURS_PER_STATION_MONTH = 24 * 30.44


def poisson_interval(k: int, conf: float = 0.95) -> tuple[float, float]:
    from scipy.stats import chi2

    a = 1 - conf
    lo = 0.0 if k == 0 else float(chi2.ppf(a / 2, 2 * k) / 2)
    hi = float(chi2.ppf(1 - a / 2, 2 * (k + 1)) / 2)
    return lo, hi


def rate_block(n: int, station_months: float) -> dict[str, Any]:
    lo, hi = poisson_interval(n)
    return {
        "windows": n,
        "per_station_month": round(n / station_months, 2),
        "ci95_per_station_month": [round(lo / station_months, 2), round(hi / station_months, 2)],
    }


def load(client: CachedWaveformClient, site: StationSite, start: datetime, end: datetime) -> Any:
    result = client.get_waveforms(
        WaveformRequest(
            site.site.network, site.site.station, site.site.location, site.site.channel, start, end
        )
    )
    if not result.ok:
        return None, None
    trace = result.stream.merge(fill_value="interpolate")[0]
    return np.asarray(trace.data, dtype=float), float(trace.stats.sampling_rate)


def event_picks(client: CachedWaveformClient) -> dict[str, Any]:
    picks: dict[str, Pick] = {}
    record: dict[str, Any] = {}
    for key, site in SITES.items():
        pre, post = EVENT_WINDOWS[key]
        start = CASCADE_ORIGIN - timedelta(seconds=pre)
        data, sr = load(client, site, start, CASCADE_ORIGIN + timedelta(seconds=post))
        if data is None:
            record[key] = {"status": "no_waveform"}
            continue
        proc = preprocess(data, sr)
        detection = sta_lta(proc, sr, preprocessed=True)
        distance = haversine_km(site.latitude, site.longitude, ZONE[0], ZONE[1])
        pick = pick_onset(detection.triggers, origin_offset_s=pre, distance_km=distance)
        if not pick.ok or pick.onset_s is None:
            record[key] = {"status": "no_pick", "reason": pick.reason}
            continue
        onset = start + timedelta(seconds=pick.onset_s)
        picks[key] = Pick(key, site.latitude, site.longitude, onset)
        record[key] = {
            "status": "ok",
            "onset_utc": onset.isoformat(),
            "distance_km": round(distance, 1),
            "reason": pick.reason,
        }
    if len(picks) == 2:
        first, second = picks["NK.KKN"], picks["IO.EVN"]
        assoc = associate(
            first, second, REGION, zone_lat=ZONE[0], zone_lon=ZONE[1], zone_radius_km=ZONE[2]
        )
        record["association"] = assoc.as_dict()
    return record


def matched(
    proc: np.ndarray,
    sr: float,
    start: datetime,
    triggers: list[Any],
    lo: datetime,
    hi: datetime,
    thr: dict[str, float],
) -> tuple[bool, bool]:
    """Any trigger in the bracket, and any such trigger whose segment also passes."""
    any_hit = False
    strict_hit = False
    for trig in triggers:
        when = start + timedelta(seconds=trig.on_s)
        if not (lo <= when <= hi):
            continue
        any_hit = True
        try:
            seg = extract(
                proc,
                sr,
                preprocessed=True,
                onset_s=trig.on_s,
                segment_s=DEFAULT.seismic.decision_segment_s,
            )
        except ValueError:
            continue
        if (
            seg.signal_present
            and np.isfinite(seg.spectral_ratio_low_high)
            and np.isfinite(seg.spectral_centroid_hz)
            and seg.spectral_ratio_low_high >= thr["lf_hf_min"]
            and seg.spectral_centroid_hz <= thr["centroid_hz_max"]
        ):
            strict_hit = True
    return any_hit, strict_hit


def false_alarm_survival(client: CachedWaveformClient, exp018: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, rec in exp018["stations"].items():
        other_key = OTHER[key]
        site, other = SITES[key], SITES[other_key]
        sm = rec["station_months"]
        rows = []
        for fa in rec["false_alarm_windows"]:
            start = datetime.fromisoformat(fa["window_start_utc"])
            end = start + timedelta(seconds=NOISE_WINDOW_S)
            data, sr = load(client, other, start, end)
            row: dict[str, Any] = {"window_start_utc": fa["window_start_utc"]}
            if data is None:
                row["status"] = "other_station_no_waveform"
                rows.append(row)
                continue
            proc = preprocess(data, sr)
            triggers = list(sta_lta(proc, sr, preprocessed=True).triggers)
            row["other_station_triggers"] = len(triggers)
            any_region = strict_region = any_zone = strict_zone = False
            for seg in fa["passing_segments"]:
                onset = start + timedelta(seconds=seg["on_s"])
                pick = Pick(key, site.latitude, site.longitude, onset)
                lo, hi = arrival_bracket(pick, other.latitude, other.longitude, REGION)
                a, s = matched(proc, sr, start, triggers, lo, hi, THRESHOLDS[other_key])
                any_region |= a
                strict_region |= s
                # Zone test: the matched trigger must also put the source in the zone.
                for trig in triggers:
                    when = start + timedelta(seconds=trig.on_s)
                    if not (lo <= when <= hi):
                        continue
                    other_pick = Pick(other_key, other.latitude, other.longitude, when)
                    first, second = (pick, other_pick) if key == "NK.KKN" else (other_pick, pick)
                    assoc = associate(
                        first,
                        second,
                        REGION,
                        zone_lat=ZONE[0],
                        zone_lon=ZONE[1],
                        zone_radius_km=ZONE[2],
                    )
                    if assoc.zone_feasible:
                        any_zone = True
                        _, s2 = matched(
                            proc,
                            sr,
                            start,
                            [trig],
                            when,
                            when,
                            THRESHOLDS[other_key],
                        )
                        strict_zone |= s2
            row.update(
                {
                    "status": "ok",
                    "matched_any_source": any_region,
                    "matched_any_source_and_classifies": strict_region,
                    "matched_zone_source": any_zone,
                    "matched_zone_source_and_classifies": strict_zone,
                }
            )
            rows.append(row)
        ok_rows = [r for r in rows if r["status"] == "ok"]
        out[key] = {
            "other_station": other_key,
            "station_months": sm,
            "false_alarm_windows_exp018": len(rec["false_alarm_windows"]),
            "other_station_unavailable": len(rows) - len(ok_rows),
            "single_station": rate_block(len(rec["false_alarm_windows"]), sm),
            "two_station_any_source": rate_block(sum(r["matched_any_source"] for r in ok_rows), sm),
            "two_station_any_source_and_classifies": rate_block(
                sum(r["matched_any_source_and_classifies"] for r in ok_rows), sm
            ),
            "two_station_zone_source": rate_block(
                sum(r["matched_zone_source"] for r in ok_rows), sm
            ),
            "two_station_zone_source_and_classifies": rate_block(
                sum(r["matched_zone_source_and_classifies"] for r in ok_rows), sm
            ),
            "windows": rows,
        }
    return out


def main() -> int:
    client = CachedWaveformClient()
    exp018 = json.loads(EXP018.read_text(encoding="utf-8"))
    results: dict[str, Any] = {
        "experiment": "exp019_two_station_association",
        "region": REGION.__dict__,
        "zone": {"lat": ZONE[0], "lon": ZONE[1], "radius_km": ZONE[2]},
        "velocity_km_s": [2.5, 6.5],
        "tolerance_s": 5.0,
        "event_2026": event_picks(client),
        "false_alarms": false_alarm_survival(client, exp018),
    }
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    ev = results["event_2026"]
    for key in SITES:
        print(f"2026 {key}: {ev.get(key)}")
    if "association" in ev:
        print(f"2026 association: {ev['association']}")
    for key, rec in results["false_alarms"].items():
        print(f"\n{key} (matched against {rec['other_station']}), {rec['station_months']} sm")
        for name in (
            "single_station",
            "two_station_any_source",
            "two_station_any_source_and_classifies",
            "two_station_zone_source",
            "two_station_zone_source_and_classifies",
        ):
            r = rec[name]
            print(
                f"  {name:<42} {r['windows']:3d} windows  {r['per_station_month']:7.2f}/sm  "
                f"CI {r['ci95_per_station_month']}"
            )
        print(f"  other station unavailable for {rec['other_station_unavailable']} window(s)")
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
