"""Experiment 011 — the headline: minutes of warning at Timure, Syabrubesi, Bidur.

**Question.** If GHADI had detected the 26 August 2026 initiation and fired an alert,
how many minutes of warning would each downstream settlement have received — and how
does that depend on the pipeline latency (detection + fusion + dissemination)?

**Design.** No network, no model uncertainty invented. Take the single calibrated
travel record (``ghadi.travel``: surge arrival 4 / 11 / 38 min at Timure / Syabrubesi /
Bidur) and subtract a warning latency, across four scenarios spanning what the pipeline
could plausibly cost. Then assemble and emit a sample CAP alert for the realistic case,
to show the headline figure travelling end-to-end into the message the system would send.

This is the M5.2 headline analysis, and it is entirely a lookup-and-subtract: the value
here is stating the number honestly with its n=1 provenance, not computing anything new.

**Re-running.** One command, fully offline and byte-identical:

    python experiments/exp011_lead_time_headline/run.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.alerting import build_alert_context  # noqa: E402
from ghadi.cap import build_cap, to_xml  # noqa: E402
from ghadi.fusion import Channel, fuse  # noqa: E402
from ghadi.travel import lead_times  # noqa: E402

REACH = "TRISHULI-R07"
DETECTED_UTC = datetime(2026, 8, 26, 2, 52, 24, tzinfo=UTC)  # refined origin, HANDOFF §6.3

# Warning-latency scenarios, in seconds. Everything between initiation and an issued
# alert: seismic wave to station, detection, fusion, CAP, dissemination hand-off.
SCENARIOS: dict[str, float] = {
    # Measured SeedLink latency floor (~16 s median) plus a lean detect+emit budget.
    "optimistic_30s": 30.0,
    # The configured default budget.
    "budget_60s": 60.0,
    # The re-scoping threshold: if the pipeline costs this much, the project is
    # retrospective-only (Blocker B4).
    "threshold_120s": 120.0,
    # What actually happened in 2026: the alert fired roughly 20 minutes late.
    "reality_2026_20min": 1200.0,
}


def main() -> None:
    results: dict[str, Any] = {
        "experiment": "exp011_lead_time_headline",
        "reach": REACH,
        "detected_utc": DETECTED_UTC.isoformat(),
        "calibration": "n=1, 26 Aug 2026; ghadi.travel observed arrivals 4/11/38 min",
        "scenarios": {},
    }

    for name, latency_s in SCENARIOS.items():
        leads = lead_times(REACH, warning_latency_s=latency_s)
        results["scenarios"][name] = {
            "warning_latency_s": latency_s,
            "settlements": [
                {
                    "settlement": lt.settlement,
                    "arrival_min": lt.arrival_min,
                    "lead_min": round(lt.lead_min, 2),
                    "actionable": lt.actionable,
                    "method": lt.method,
                }
                for lt in leads
            ],
        }

    # Emit a sample CAP for the budget scenario, to show the number reaching the message.
    decision = fuse(
        [
            Channel("seismic_kkn", 0.92, independence_group="seismic"),
            Channel("gauge_timure", 0.88, independence_group="hydro", alive=True),
        ]
    )
    context = build_alert_context(
        event_id="NPL-2026-08-26-BHOTEKOSHI-001",
        detected_utc=DETECTED_UTC,
        reach=REACH,
        model_version="sta_lta@v0.1.0",
        warning_latency_s=SCENARIOS["budget_60s"],
        exposed_population=1240,
    )
    sample_cap = to_xml(build_cap(decision, context))
    results["sample_cap_budget_60s"] = sample_cap

    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Console summary.
    print("Minutes of warning delivered (26 Aug 2026 calibration, n=1):\n")
    header = f"{'scenario':<22}" + "".join(f"{lt.settlement:>13}" for lt in lead_times(REACH))
    print(header)
    for name, latency_s in SCENARIOS.items():
        leads = lead_times(REACH, warning_latency_s=latency_s)
        cells = "".join(f"{lt.lead_min:>10.1f} min" for lt in leads)
        print(f"{name:<22}{cells}")
    print(f"\nSample CAP (budget 60 s) and full table -> {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
