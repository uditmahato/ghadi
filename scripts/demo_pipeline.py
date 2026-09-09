"""End-to-end pipeline demo, fully offline.

Runs a 26-August-2026-like window through the whole orchestration — seismic
classification, teleseism cross-check, gauge corroboration, fusion, lead time, CAP
emission — and writes a hash-chained audit log, then verifies it. No network, no live
feed: this is the software system running end to end, which is what M5 completes. The
live SeedLink source (issue 0.1) is the one piece still outside.

    python scripts/demo_pipeline.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.hydro import synthetic_surge  # noqa: E402
from ghadi.service import (  # noqa: E402
    AuditLog,
    GaugeObservation,
    HealthMonitor,
    WindowObservation,
    run_over,
    verify_chain,
)

REACH = "TRISHULI-R07"
MODEL = "sta_lta@v0.1.0+classify@v0.1.0"
DETECTED = datetime(2026, 8, 26, 2, 52, 24, tzinfo=UTC)


def main() -> None:
    times, stage = synthetic_surge()
    window = WindowObservation(
        window_start_utc=DETECTED - timedelta(seconds=120),
        detected_utc=DETECTED,
        # Cascade decision-segment features (exp005): low-frequency, extended source.
        segment_lf_hf=4.9188,
        segment_centroid_hz=1.8852,
        seismic_sensor_alive=True,
        gauge=GaugeObservation(
            times.tolist(), stage.tolist(), sensor_alive=True, name="gauge_timure"
        ),
        event_id="NPL-2026-08-26-BHOTEKOSHI-001",
    )

    audit_path = REPO_ROOT / "scratch_audit.jsonl"
    if audit_path.exists():
        audit_path.unlink()
    health = HealthMonitor()
    (outcome,) = run_over(
        [window], reach=REACH, model_version=MODEL, audit_log=AuditLog(audit_path), health=health
    )

    print("=== GHADI end-to-end (offline) ===")
    print(f"decision tier : {outcome.decision.tier.value}")
    print(f"fused p       : {outcome.decision.probability:.2f}")
    print(f"channels alive: {', '.join(outcome.decision.channels_alive)}")
    print(f"suppressed    : {outcome.suppression.suppressed}")
    if outcome.lead_times_min:
        print("minutes of warning:")
        for settlement, lead in sorted(outcome.lead_times_min.items(), key=lambda kv: kv[1]):
            print(f"  {settlement:<12} {lead:6.1f} min")
    print(f"alert raised  : {outcome.alert_xml is not None}")
    print(f"audit chain   : {'VERIFIED' if verify_chain(audit_path) else 'BROKEN'}")
    print(f"health blind  : {health.blind}")
    print(f"\naudit log -> {audit_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
