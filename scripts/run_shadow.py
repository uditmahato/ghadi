"""Run GHADI in shadow mode: decisions are recorded, nothing is sent (issue #30).

Two feeds, one loop:

    # Replay a past window through the real time path, from the local cache
    GHADI_OFFLINE=1 python scripts/run_shadow.py replay \
        --start 2026-08-26T02:45:00Z --minutes 20

    # Connect to a live SeedLink server and run until stopped
    python scripts/run_shadow.py live --hours 24 --audit data/shadow/audit.jsonl

Shadow is tier T0 in the handoff: the system decides, the decision goes into the
hash chained audit log, and nothing leaves the machine. There is no flag that turns
this into alerting, because no delivery path exists yet (issue #36).

The live run is also the latency measurement the project is gated on (issue #8): each
window reports the worst packet delay that built it, and the summary prints the
distribution.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ghadi.config import KAKANI, STATION_SITES  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.live import FeedStats, LiveConfig, WindowVerdict, run_shadow  # noqa: E402
from ghadi.service import AuditLog, HealthMonitor, ServiceOutcome  # noqa: E402
from ghadi.sources import (  # noqa: E402
    DEFAULT_SEEDLINK_SERVER,
    ReplaySource,
    SeedLinkSource,
    packets_from_trace,
)
from ghadi.stream import Packet  # noqa: E402

REACH = "TRISHULI-R07"


def parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def cached_packets(
    station_key: str, start: datetime, minutes: float, packet_s: float, delay_s: float
) -> tuple[list[Packet], float]:
    """Cut a cached archive window into packets, as a feed would have delivered it."""
    site = STATION_SITES[station_key]
    client = CachedWaveformClient()
    end = start + timedelta(minutes=minutes)
    result = client.get_waveforms(
        WaveformRequest(
            site.site.network, site.site.station, site.site.location, site.site.channel, start, end
        )
    )
    if not result.ok:
        raise SystemExit(f"no waveform for {station_key} at {start.isoformat()}: {result.error}")
    trace = result.stream.merge(fill_value="interpolate")[0]
    sr = float(trace.stats.sampling_rate)
    data = np.asarray(trace.data, dtype=float)
    first = trace.stats.starttime.datetime.replace(tzinfo=UTC)
    return (
        packets_from_trace(
            data, sr, first, station=station_key, packet_s=packet_s, delay_s=delay_s
        ),
        sr,
    )


def report(verdict: WindowVerdict) -> None:
    window = verdict.window
    flag = " STALE" if verdict.stale else ""
    print(
        f"  {window.start_utc.isoformat()} {verdict.reason:<18} "
        f"usable {window.usable_fraction:5.1%} delay {window.max_delay_s:6.1f}s{flag}",
        flush=True,
    )


def summarise(outcomes: list[ServiceOutcome], stats: FeedStats, health: HealthMonitor) -> None:
    print()
    print(f"feed        : {json.dumps(stats.as_dict())}")
    print(f"decisions   : {len(outcomes)}")
    for outcome in outcomes:
        tier = outcome.decision.tier.value
        print(
            f"  {outcome.audit.payload['detected_utc']} {tier:<8} "
            f"p={outcome.decision.probability:.2f} {outcome.decision.rationale[:90]}"
        )
    print(f"alerts      : {health.alerts_raised} (shadow mode: none were sent)")
    print(f"suppressed  : {health.suppressed}")
    if stats.windows and stats.delays_s:
        p95 = stats.percentile(95)
        verdict = "within" if p95 <= 120.0 else "above"
        print(f"latency p95 : {p95:.1f}s, {verdict} the 120 s viability threshold (issue #8)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--audit", type=Path, default=None, help="audit log path (JSON lines)")
    common.add_argument("--station", default=KAKANI.key, choices=sorted(STATION_SITES))
    common.add_argument("--quiet", action="store_true", help="only print the summary")

    rep = sub.add_parser("replay", parents=[common], help="replay a cached archive window")
    rep.add_argument("--start", required=True, type=parse_utc, help="window start, UTC")
    rep.add_argument("--minutes", type=float, default=20.0)
    rep.add_argument("--packet-s", type=float, default=10.0, help="samples per feed packet")
    rep.add_argument("--delay-s", type=float, default=6.0, help="assumed feed delay")
    rep.add_argument("--speed", type=float, default=0.0, help="0 is as fast as possible")

    live = sub.add_parser("live", parents=[common], help="connect to a SeedLink server")
    live.add_argument("--server", default=DEFAULT_SEEDLINK_SERVER)
    live.add_argument("--hours", type=float, default=1.0)

    args = parser.parse_args(argv)
    stats = FeedStats()
    health = HealthMonitor()
    audit = AuditLog(args.audit) if args.audit else None
    if args.audit:
        args.audit.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "replay":
        packets, sr = cached_packets(
            args.station, args.start, args.minutes, args.packet_s, args.delay_s
        )
        print(f"replaying {len(packets)} packets from {args.station} at {sr:g} Hz")
        source: ReplaySource | SeedLinkSource = ReplaySource(packets, speed=args.speed)
        cfg = LiveConfig(station=args.station, sampling_rate=sr)
    else:
        site = STATION_SITES[args.station]
        source = SeedLinkSource(station=site.site, server=args.server, key=args.station)
        cfg = LiveConfig(station=args.station)  # rate comes from the first packet
        print(f"connecting to {args.server} for {args.station}; stop with Ctrl-C")
        _stop_after(source, args.hours)

    try:
        outcomes = run_shadow(
            source,
            reach=REACH,
            model_version="shadow",
            live=cfg,
            stats=stats,
            audit_log=audit,
            health=health,
            on_verdict=None if args.quiet else report,
        )
    except KeyboardInterrupt:
        print("\nstopped by operator")
        outcomes = []

    summarise(outcomes, stats, health)
    if audit is not None:
        print(f"audit       : {args.audit}")
    return 0


def _stop_after(source: SeedLinkSource, hours: float) -> None:
    """Ask a live feed to stop after a fixed run, so a timed run ends by itself."""
    import threading

    threading.Timer(hours * 3600.0, source.stop).start()


if __name__ == "__main__":
    sys.exit(main())
