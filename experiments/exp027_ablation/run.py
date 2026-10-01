"""Experiment 027: what does each rule add? One table, one basis.

**Question.** The rules were measured one at a time, in different experiments, on
slightly different bases. A reader needs one table: the same noise corpora, the same
operating point, each rule added in turn, each rule alone, and each rule left out.

**Design.** Fully offline, from results already committed:

* the windows and triggers of exp018,
* the per segment measurements of exp022 (spectral values, H/V over the decision
  segment, and whether the other station triggered at a time fitting the basin box),
* the M4.5 and above catalogue of exp024 for the distant earthquake check.

Operating point: the defaults, a 20 percent margin on the 2026 values. A window is a
false alarm under a set of rules if any of its trigger segments passes every rule in
the set. Rates are per station month with exact Poisson intervals.

The rules:

* **spectral**: LF/HF and centroid over the decision segment.
* **catalogue**: the onset is not inside the phase window of an M5.5 earthquake
  anywhere or an M5.0 within 80 degrees.
* **hv**: the horizontal to vertical energy ratio over the segment.
* **partner**: the other station triggered at a time fitting a source in the basin box.

    python experiments/exp027_ablation/run.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import DEFAULT, EVEREST, KAKANI  # noqa: E402
from ghadi.teleseism import (  # noqa: E402
    Origin,
    epicentral_distance_deg,
    magnitude_applies,
    phase_window,
)

EXP = REPO_ROOT / "experiments"
MARGIN = 0.2
SITES = {"NK.KKN": KAKANI, "IO.EVN": EVEREST}
EXTRA = ("catalogue", "hv", "partner")


def poisson_interval(k: int, conf: float = 0.95) -> tuple[float, float]:
    from scipy.stats import chi2

    a = 1 - conf
    lo = 0.0 if k == 0 else float(chi2.ppf(a / 2, 2 * k) / 2)
    hi = float(chi2.ppf(1 - a / 2, 2 * (k + 1)) / 2)
    return lo, hi


def block(n: int, sm: float) -> dict[str, Any]:
    lo, hi = poisson_interval(n)
    return {
        "windows": n,
        "per_station_month": round(n / sm, 2),
        "ci95": [round(lo / sm, 2), round(hi / sm, 2)],
    }


def main() -> int:
    exp018 = json.loads(
        (EXP / "exp018_io_evn_false_alarm_rate" / "results.json").read_text("utf-8")
    )
    exp022 = json.loads((EXP / "exp022_margin_and_joint_rules" / "results.json").read_text("utf-8"))
    cat = json.loads(
        (EXP / "exp024_suppression_threshold" / "catalogue_m45.json").read_text("utf-8")
    )
    origins = [
        Origin(datetime.fromisoformat(r["time_utc"]), r["latitude"], r["longitude"], r["magnitude"])
        for r in cat
    ]
    sup = DEFAULT.suppression
    results: dict[str, Any] = {"experiment": "exp027_ablation", "margin": MARGIN, "stations": {}}

    for key, site in SITES.items():
        st22 = exp022["stations"][key]
        sm = st22["station_months"]
        thr = st22["by_margin"][str(MARGIN)]["thresholds"]
        windows_set_aside = []
        for o in origins:
            deg = epicentral_distance_deg(site.latitude, site.longitude, o)
            if magnitude_applies(
                o.magnitude, deg, sup.min_magnitude, sup.near_min_magnitude, sup.near_deg
            ):
                opens, closes, _ = phase_window(o, site.latitude, site.longitude)
                windows_set_aside.append((opens, closes))

        def catalogue_ok(
            when: datetime, aside: list[tuple[datetime, datetime]] = windows_set_aside
        ) -> bool:
            return not any(a <= when <= b for a, b in aside)

        rows = []
        for w in st22["windows"]:
            start = datetime.fromisoformat(w["window_start_utc"])
            segs = []
            for s in w["segments"]:
                if not (
                    s["lf_hf"] >= thr["lf_hf_min"] and s["centroid_hz"] <= thr["centroid_hz_max"]
                ):
                    continue
                segs.append(
                    {
                        "catalogue": catalogue_ok(start + timedelta(seconds=s["on_s"])),
                        "hv": s["hv_segment"] is not None and s["hv_segment"] >= thr["hv_min"],
                        "partner": bool(s["other_basin_box"]),
                    }
                )
            if segs:
                rows.append({"segments": segs, "other_available": w["other_station_available"]})

        def count(rules: tuple[str, ...], rows: list[dict[str, Any]] = rows) -> int:
            return sum(1 for r in rows if any(all(s[x] for x in rules) for s in r["segments"]))

        def count_with_fallback(rows: list[dict[str, Any]] = rows) -> int:
            """All rules where the partner had data; catalogue and H/V alone where not."""
            n = 0
            for r in rows:
                rules = EXTRA if r["other_available"] else ("catalogue", "hv")
                if any(all(s[x] for x in rules) for s in r["segments"]):
                    n += 1
            return n

        triggered = exp018["stations"][key]["layers"]["sta_lta_trigger"]["windows"]
        table: dict[str, Any] = {
            "station_months": sm,
            "usable_windows": st22["usable_windows"],
            "cumulative": {
                "trigger_only": block(triggered, sm),
                "spectral": block(count(()), sm),
                "spectral+catalogue": block(count(("catalogue",)), sm),
                "spectral+catalogue+hv": block(count(("catalogue", "hv")), sm),
                "spectral+catalogue+hv+partner": block(count(("catalogue", "hv", "partner")), sm),
            },
            "one_rule_added_to_spectral": {x: block(count((x,)), sm) for x in EXTRA},
            "one_rule_left_out": {
                x: block(count(tuple(y for y in EXTRA if y != x)), sm) for x in EXTRA
            },
            "pairs": {"+".join(c): block(count(c), sm) for c in combinations(EXTRA, 2)},
            "partner_unavailable_among_spectral": sum(1 for r in rows if not r["other_available"]),
            "all_rules_with_fallback_when_partner_missing": block(count_with_fallback(), sm),
        }
        results["stations"][key] = table
        print(f"{key} ({sm} station months, {st22['usable_windows']} windows)")
        for section in ("cumulative", "one_rule_added_to_spectral", "one_rule_left_out"):
            print(f"  {section}")
            for name, b in table[section].items():
                print(
                    f"     {name:<34} {b['windows']:4d}  {b['per_station_month']:8.2f}  {b['ci95']}"
                )
        print(
            f"  partner unavailable among spectral: {table['partner_unavailable_among_spectral']}"
        )
        fb = table["all_rules_with_fallback_when_partner_missing"]
        print(f"  all rules, falling back when the partner is missing: {fb}")

    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
