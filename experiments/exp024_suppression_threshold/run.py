"""Experiment 024: how low should the distant earthquake threshold go?

**Question.** The live shadow run staged one Advisory in its first 20 hours, and it was
an M5.2 earthquake near Yemen, 36 degrees away, whose waves reached Kakani at the moment
of the trigger. The suppressor only considers M5.5 and above (exp006). Lowering the
threshold catches more of these, and it also spends more time with the seismic channel
set aside, during which a real slope failure would not be seen seismically. What does
each rule buy and cost?

**Design.** The USGS catalogue at M4.5 and above for the noise corpus period. Three
rules:

* **A:** M5.5 and above at any distance (today's rule).
* **B:** M5.0 and above at any distance.
* **C:** M5.5 and above at any distance, and M5.0 and above within 60 degrees. A smaller
  earthquake carries less energy and is only a threat when it is closer.

For each rule and station:

* **Set aside time**: the share of the period inside any origin's phase window.
* **False alarms explained**: how many exp018 false alarm segments fall in a window.
* **Earthquake overlap explained**: nothing here; regional earthquakes are a different
  check.

And the live case: whether the 26 September 2026 Advisory is explained under each rule.

    python experiments/exp024_suppression_threshold/run.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import EVEREST, KAKANI, StationSite  # noqa: E402
from ghadi.origins_feed import fetch_usgs  # noqa: E402
from ghadi.teleseism import Origin, epicentral_distance_deg, phase_window  # noqa: E402

EXP018 = REPO_ROOT / "experiments" / "exp018_io_evn_false_alarm_rate" / "results.json"
CACHE = Path(__file__).resolve().parent / "catalogue_m45.json"
PERIOD = (datetime(2024, 1, 1, tzinfo=UTC), datetime(2026, 8, 1, tzinfo=UTC))
SITES: dict[str, StationSite] = {"NK.KKN": KAKANI, "IO.EVN": EVEREST}
LIVE_CASE = datetime(2026, 9, 26, 16, 40, 26, tzinfo=UTC)
NEAR_DEG = 60.0


def rule_a(mag: float, deg: float) -> bool:
    return mag >= 5.5


def rule_b(mag: float, deg: float) -> bool:
    return mag >= 5.0


def rule_c(mag: float, deg: float) -> bool:
    return mag >= 5.5 or (mag >= 5.0 and deg <= NEAR_DEG)


def near_rule(near_deg: float) -> Any:
    return lambda mag, deg: mag >= 5.5 or (mag >= 5.0 and deg <= near_deg)


RULES = {
    "A_m55_any": rule_a,
    "B_m50_any": rule_b,
    "C_m55_any_or_m50_within_60deg": rule_c,
    "C_within_40deg": near_rule(40.0),
    "C_within_80deg": near_rule(80.0),
    "C_within_100deg": near_rule(100.0),
}


def load_catalogue() -> list[Origin]:
    if CACHE.exists():
        raw = json.loads(CACHE.read_text(encoding="utf-8"))
    else:
        raw = []
        cursor = PERIOD[0] - timedelta(hours=3)
        end = max(PERIOD[1], LIVE_CASE + timedelta(hours=1))
        while cursor < end:
            stop = min(cursor + timedelta(days=120), end)
            for o in fetch_usgs(cursor, stop, 4.5):
                raw.append(
                    {
                        "time_utc": o.time_utc.isoformat(),
                        "latitude": o.latitude,
                        "longitude": o.longitude,
                        "magnitude": o.magnitude,
                        "event_id": o.event_id,
                        "place": o.place,
                    }
                )
            print(f"   fetched to {stop.date()}: {len(raw)} origins", flush=True)
            cursor = stop
        CACHE.write_text(json.dumps(raw), encoding="utf-8")
    return [
        Origin(
            datetime.fromisoformat(r["time_utc"]),
            r["latitude"],
            r["longitude"],
            r["magnitude"],
            r.get("event_id", ""),
            r.get("place", ""),
        )
        for r in raw
    ]


def windows_for(
    origins: list[Origin], site: StationSite, rule: Any
) -> list[tuple[datetime, datetime]]:
    out = []
    for o in origins:
        deg = epicentral_distance_deg(site.latitude, site.longitude, o)
        if rule(o.magnitude, deg):
            opens, closes, _ = phase_window(o, site.latitude, site.longitude)
            out.append((opens, closes))
    return sorted(out)


def covered_fraction(
    windows: list[tuple[datetime, datetime]], start: datetime, end: datetime
) -> float:
    total = 0.0
    cur_s: datetime | None = None
    cur_e: datetime | None = None
    for s, e in windows:
        s, e = max(s, start), min(e, end)
        if s >= e:
            continue
        if cur_e is None or s > cur_e:
            if cur_s is not None and cur_e is not None:
                total += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_s is not None and cur_e is not None:
        total += (cur_e - cur_s).total_seconds()
    return total / (end - start).total_seconds()


def inside(when: datetime, windows: list[tuple[datetime, datetime]]) -> bool:
    return any(s <= when <= e for s, e in windows)


def main() -> int:
    origins = load_catalogue()
    exp018 = json.loads(EXP018.read_text(encoding="utf-8"))
    results: dict[str, Any] = {
        "experiment": "exp024_suppression_threshold",
        "period": [PERIOD[0].isoformat(), PERIOD[1].isoformat()],
        "origins_m45": len(origins),
        "near_deg": NEAR_DEG,
        "stations": {},
    }
    for key, site in SITES.items():
        segs = [
            (
                datetime.fromisoformat(w["window_start_utc"]) + timedelta(seconds=s["on_s"]),
                w["window_start_utc"],
            )
            for w in exp018["stations"][key]["false_alarm_windows"]
            for s in w["passing_segments"]
        ]
        by_rule = {}
        for name, rule in RULES.items():
            wins = windows_for(origins, site, rule)
            explained_windows = sorted({w for when, w in segs if inside(when, wins)})
            in_period = [x for x in wins if x[1] >= PERIOD[0] and x[0] <= PERIOD[1]]
            by_rule[name] = {
                "origins_in_period": len(in_period),
                "set_aside_fraction": round(covered_fraction(wins, *PERIOD), 4),
                "false_alarm_segments_explained": sum(1 for when, _ in segs if inside(when, wins)),
                "false_alarm_windows_explained": len(explained_windows),
                "of_false_alarm_windows": len(exp018["stations"][key]["false_alarm_windows"]),
                "live_case_2026_09_26_explained": inside(LIVE_CASE, wins)
                if key == "NK.KKN"
                else None,
            }
        results["stations"][key] = by_rule
        print(key)
        for name, rec in by_rule.items():
            print(f"   {name}: {rec}")
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
