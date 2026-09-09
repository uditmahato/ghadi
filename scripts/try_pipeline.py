"""Interactive tester for the GHADI pipeline — run one window with your own inputs.

Fully offline. Turn the knobs and watch the decision, the suppression, the channels,
the lead times, and (optionally) the emitted CAP alert change.

Examples:
    python scripts/try_pipeline.py                         # the 2026-like WARNING
    python scripts/try_pipeline.py --quiet-river           # seismic only
    python scripts/try_pipeline.py --earthquake            # earthquake-like features
    python scripts/try_pipeline.py --teleseism             # distant quake -> suppressed
    python scripts/try_pipeline.py --dead-gauge            # gauge died, no anomaly seen
    python scripts/try_pipeline.py --dead-station --quiet-river   # both blind
    python scripts/try_pipeline.py --latency 600           # slow pipeline eats the lead
    python scripts/try_pipeline.py --show-alert            # print the full CAP XML
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ghadi.config import PRIMARY_STATION_LAT, PRIMARY_STATION_LON  # noqa: E402
from ghadi.hydro import synthetic_surge  # noqa: E402
from ghadi.service import GaugeObservation, WindowObservation, process_window  # noqa: E402
from ghadi.teleseism import Origin  # noqa: E402

# Cascade decision-segment features (exp005) vs an earthquake-like window.
CASCADE = (4.9188, 1.8852)
EARTHQUAKE = (1.66, 3.04)
DETECTED = datetime(2026, 8, 26, 2, 52, 24, tzinfo=UTC)


def build_gauge(args: argparse.Namespace) -> GaugeObservation | None:
    if args.no_gauge:
        return None
    if args.quiet_river:
        times = np.arange(0.0, 3600.0, 60.0)
        noise = np.random.default_rng(7).normal(0, 0.01, times.size)
        stage = np.full_like(times, 2.0) + noise
    elif args.dead_gauge:
        # Sensor died early, before the surge it was measuring crossed threshold.
        times, stage = synthetic_surge(destroy_at_s=300.0)
        return GaugeObservation(
            times.tolist(), stage.tolist(), sensor_alive=False, name="gauge_timure"
        )
    else:
        times, stage = synthetic_surge()
    return GaugeObservation(times.tolist(), stage.tolist(), sensor_alive=True, name="gauge_timure")


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--earthquake", action="store_true", help="earthquake-like features")
    p.add_argument("--lf-hf", type=float, help="override segment LF/HF")
    p.add_argument("--centroid", type=float, help="override segment centroid (Hz)")
    p.add_argument("--quiet-river", action="store_true", help="flat gauge, no surge")
    p.add_argument("--dead-gauge", action="store_true", help="gauge sensor died with no anomaly")
    p.add_argument("--no-gauge", action="store_true", help="no gauge channel at all")
    p.add_argument("--dead-station", action="store_true", help="seismic station offline")
    p.add_argument("--teleseism", action="store_true", help="inject a distant M6.5 origin")
    p.add_argument("--latency", type=float, default=60.0, help="warning latency s (default 60)")
    p.add_argument("--show-alert", action="store_true", help="print the full CAP XML")
    args = p.parse_args()

    lf_hf, centroid = EARTHQUAKE if args.earthquake else CASCADE
    if args.lf_hf is not None:
        lf_hf = args.lf_hf
    if args.centroid is not None:
        centroid = args.centroid

    origins: tuple[Origin, ...] = ()
    if args.teleseism:
        origins = (
            Origin(time_utc=DETECTED, latitude=PRIMARY_STATION_LAT, longitude=PRIMARY_STATION_LON,
                   magnitude=6.5, place="injected teleseism"),
        )

    obs = WindowObservation(
        window_start_utc=DETECTED - timedelta(seconds=120),
        detected_utc=DETECTED,
        segment_lf_hf=lf_hf,
        segment_centroid_hz=centroid,
        seismic_sensor_alive=not args.dead_station,
        gauge=build_gauge(args),
        origins=origins,
        event_id="NPL-2026-08-26-BHOTEKOSHI-001",
    )

    outcome = process_window(
        obs, reach="TRISHULI-R07", model_version="sta_lta@v0.1.0+classify@v0.1.0",
        warning_latency_s=args.latency,
    )

    gauge_name = "none" if obs.gauge is None else obs.gauge.name
    print("=== inputs ===")
    print(f"seismic LF/HF={lf_hf}  centroid={centroid} Hz  station_alive={not args.dead_station}")
    print(f"gauge={gauge_name}  teleseism={args.teleseism}  latency={args.latency:.0f}s")
    print("\n=== decision ===")
    print(f"tier          : {outcome.decision.tier.value}")
    print(f"fused p       : {outcome.decision.probability:.2f}")
    print(f"channels alive: {', '.join(outcome.decision.channels_alive) or '(none)'}")
    print(f"channels dead : {', '.join(outcome.decision.channels_dead) or '(none)'}")
    print(f"suppressed    : {outcome.suppression.suppressed}  ({outcome.suppression.reason})")
    print(f"rationale     : {outcome.decision.rationale}")
    if outcome.lead_times_min:
        print("minutes of warning:")
        for s, lead in sorted(outcome.lead_times_min.items(), key=lambda kv: kv[1]):
            print(f"  {s:<12} {lead:6.1f} min")
    print(f"alert raised  : {outcome.alert_xml is not None}")
    if args.show_alert and outcome.alert_xml:
        print("\n=== CAP alert ===")
        print(outcome.alert_xml)


if __name__ == "__main__":
    main()
