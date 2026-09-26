"""Run GHADI in shadow mode: decisions are recorded, nothing is sent (issues #30, #34).

Two feeds, one loop:

    # Replay a past window through the real time path, from the local cache
    GHADI_OFFLINE=1 python scripts/run_shadow.py replay \
        --start 2026-08-26T02:42:10Z --minutes 45

    # Connect to a live SeedLink server and run for a day
    python scripts/run_shadow.py live --hours 24

    # Run as a service, from a settings file, until stopped
    python scripts/run_shadow.py live --settings deploy/ghadi.toml --hours 0

Shadow is tier T0 in the handoff: the system decides, the decision goes into the hash
chained audit log, and nothing leaves the machine. Every alert the system would have
raised is *staged* for a person; ``scripts/outbox.py`` is where that person approves or
rejects it (issue #36). Nothing in this process delivers anything.

While it runs the service writes ``status.json`` in the state directory after every
window, and answers ``GET /health`` on the configured port. The live run is also the
latency measurement the project is gated on (issue #8): each window reports the worst
packet delay that built it, and the summary prints the distribution.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ghadi.config import STATION_SITES, Station  # noqa: E402
from ghadi.delivery import FileSink, Outbox  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.health import HealthServer  # noqa: E402
from ghadi.live import (  # noqa: E402
    FeedStats,
    LiveConfig,
    PartnerConfig,
    WindowVerdict,
    horizontal_key,
    run_shadow,
)
from ghadi.service import AuditLog, HealthMonitor, ServiceOutcome, verify_chain  # noqa: E402
from ghadi.settings import SiteSettings, load_settings  # noqa: E402
from ghadi.sources import ReplaySource, SeedLinkSource, packets_from_trace  # noqa: E402
from ghadi.stream import Packet  # noqa: E402

RECENT = 20


def parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def cached_packets(
    station_key: str,
    start: datetime,
    minutes: float,
    packet_s: float,
    delay_s: float,
    *,
    component: str = "Z",
    key: str | None = None,
    required: bool = True,
) -> tuple[list[Packet], float]:
    """Cut a cached archive window into packets, as a feed would have delivered it."""
    site = STATION_SITES[station_key]
    client = CachedWaveformClient()
    end = start + timedelta(minutes=minutes)
    channel = site.site.channel[:2] + component
    result = client.get_waveforms(
        WaveformRequest(
            site.site.network, site.site.station, site.site.location, channel, start, end
        )
    )
    if not result.ok:
        if not required:
            return [], 0.0
        raise SystemExit(f"no waveform for {station_key} at {start.isoformat()}: {result.error}")
    trace = result.stream.merge(fill_value="interpolate")[0]
    sr = float(trace.stats.sampling_rate)
    data = np.asarray(trace.data, dtype=float)
    first = trace.stats.starttime.datetime.replace(tzinfo=UTC)
    packets = packets_from_trace(
        data, sr, first, station=key or station_key, packet_s=packet_s, delay_s=delay_s
    )
    return packets, sr


def replay_packets(settings: SiteSettings, args: argparse.Namespace) -> tuple[list[Packet], float]:
    """Primary vertical, its horizontals if asked, and the partner, merged by arrival."""
    packets, sr = cached_packets(
        settings.station_key, args.start, args.minutes, args.packet_s, args.delay_s
    )
    if settings.horizontals:
        for comp in ("N", "E"):
            extra, _ = cached_packets(
                settings.station_key,
                args.start,
                args.minutes,
                args.packet_s,
                args.delay_s,
                component=comp,
                key=horizontal_key(settings.station_key, comp),
                required=False,
            )
            if not extra:
                print(f"no {comp} component in the cache for this window; H/V rule off")
            packets += extra
    if settings.partner_key:
        extra, _ = cached_packets(
            settings.partner_key,
            args.start,
            args.minutes,
            args.packet_s,
            args.delay_s,
            required=False,
        )
        if not extra:
            print(f"no partner waveform ({settings.partner_key}) in the cache; no corroboration")
        packets += extra
    packets.sort(key=lambda p: p.received_utc)
    return packets, sr


class ShadowState:
    """Everything the status file and the health endpoint report."""

    def __init__(
        self,
        settings: SiteSettings,
        mode: str,
        stats: FeedStats,
        health: HealthMonitor,
        source: SeedLinkSource | None,
        outbox: Outbox,
        quiet: bool,
    ) -> None:
        self.settings = settings
        self.mode = mode
        self.stats = stats
        self.health = health
        self.source = source
        self.outbox = outbox
        self.quiet = quiet
        self.started_utc = datetime.now(tz=UTC)
        self.last_window_utc: datetime | None = None
        self.last_feed_utc: datetime | None = None
        self.recent: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def on_verdict(self, verdict: WindowVerdict) -> None:
        window = verdict.window
        with self.lock:
            self.last_window_utc = window.end_utc
            self.last_feed_utc = datetime.now(tz=UTC)
        if not self.quiet:
            flag = " STALE" if verdict.stale else ""
            print(
                f"  {window.start_utc.isoformat()} {verdict.reason:<18} "
                f"usable {window.usable_fraction:5.1%} delay {window.max_delay_s:6.1f}s{flag}",
                flush=True,
            )
        self.write_status()

    def on_outcome(self, outcome: ServiceOutcome) -> None:
        staged = self.outbox.stage(outcome)
        entry = {
            "detected_utc": outcome.audit.payload["detected_utc"],
            "tier": outcome.decision.tier.value,
            "probability": round(outcome.decision.probability, 3),
            "rationale": outcome.decision.rationale,
            "suppressed": outcome.suppression.suppressed,
            "staged_id": staged.staged_id if staged else None,
        }
        with self.lock:
            self.recent.append(entry)
            del self.recent[:-RECENT]
        print(
            f"  decision {entry['detected_utc']} {entry['tier']} p={entry['probability']:.2f}"
            + (f"  staged for a person as {staged.staged_id}" if staged else ""),
            flush=True,
        )
        self.write_status()

    def snapshot(self) -> dict[str, Any]:
        now = datetime.now(tz=UTC)
        with self.lock:
            last_feed = self.last_feed_utc
            recent = list(self.recent)
            last_window = self.last_window_utc
        feed_age_s = (now - last_feed).total_seconds() if last_feed else None
        chain_ok = verify_chain(self.settings.audit_path)
        stale = self.mode == "live" and feed_age_s is not None and feed_age_s > 600.0
        never = (
            self.mode == "live"
            and last_feed is None
            and ((now - self.started_utc).total_seconds() > 600.0)
        )
        return {
            "ok": chain_ok and not stale and not never,
            "mode": self.mode,
            "shadow": True,
            "station": self.settings.station_key,
            "server": self.settings.server if self.mode == "live" else None,
            "reach": self.settings.reach,
            "started_utc": self.started_utc.isoformat(),
            "updated_utc": now.isoformat(),
            "last_window_end_utc": last_window.isoformat() if last_window else None,
            "seconds_since_last_window": round(feed_age_s, 1) if feed_age_s else None,
            "feed": self.stats.as_dict(),
            "reconnections": self.source.reconnections if self.source else 0,
            "dropped_packets": self.source.dropped_packets if self.source else 0,
            "decisions": {
                "windows_seen": self.health.windows_seen,
                "alerts_staged": self.health.alerts_raised,
                "suppressed": self.health.suppressed,
                "last_detected_utc": self.health.last_detected_utc,
                "blind": self.health.blind,
            },
            "audit_chain_ok": chain_ok,
            "staged_waiting_for_a_person": len(self.outbox.pending()),
            "recent_decisions": recent,
        }

    def write_status(self) -> None:
        path = self.settings.status_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.snapshot(), indent=2, default=str), encoding="utf-8")
        tmp.replace(path)


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
    print(f"alerts      : {health.alerts_raised} staged for a person; none sent (shadow mode)")
    print(f"suppressed  : {health.suppressed}")
    if stats.delays_s:
        p95 = stats.percentile(95)
        verdict = "within" if p95 <= 120.0 else "above"
        print(f"latency p95 : {p95:.1f}s, {verdict} the 120 s viability threshold (issue #8)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--settings", type=Path, default=None, help="site settings TOML")
    common.add_argument("--station", default=None, choices=sorted(STATION_SITES))
    common.add_argument("--state-dir", type=Path, default=None, help="overrides the settings")
    common.add_argument("--quiet", action="store_true", help="only print decisions and summary")

    rep = sub.add_parser("replay", parents=[common], help="replay a cached archive window")
    rep.add_argument("--start", required=True, type=parse_utc, help="window start, UTC")
    rep.add_argument("--minutes", type=float, default=20.0)
    rep.add_argument("--packet-s", type=float, default=10.0, help="samples per feed packet")
    rep.add_argument("--delay-s", type=float, default=6.0, help="assumed feed delay")
    rep.add_argument("--speed", type=float, default=0.0, help="0 is as fast as possible")

    live = sub.add_parser("live", parents=[common], help="connect to a SeedLink server")
    live.add_argument("--server", default=None, help="overrides the settings")
    live.add_argument("--hours", type=float, default=1.0, help="0 runs until stopped")

    args = parser.parse_args(argv)
    settings = load_settings(args.settings)
    if args.station:
        settings = _replace(settings, station_key=args.station)
    if args.state_dir:
        settings = _replace(settings, state_dir=args.state_dir.resolve())
    if args.mode == "live" and args.server:
        settings = _replace(settings, server=args.server)
    if args.mode == "replay":
        # A replay must never mix its records into a live deployment's state.
        settings = _replace(settings, state_dir=settings.state_dir / "replay")

    settings.state_dir.mkdir(parents=True, exist_ok=True)
    stats = FeedStats()
    health = HealthMonitor()
    audit = AuditLog(settings.audit_path)
    outbox = Outbox(
        settings.delivery_log_path,
        [FileSink(settings.outbox_dir)],
        staging_dir=settings.staging_dir,
    )
    partner_cfg: PartnerConfig | None = None
    if settings.partner_key:
        partner_site = STATION_SITES[settings.partner_key]
        partner_cfg = PartnerConfig(
            settings.partner_key, partner_site.latitude, partner_site.longitude
        )
    live_cfg = LiveConfig(
        station=settings.station_key,
        window_s=settings.window_s,
        hop_s=settings.hop_s,
        max_gap_fraction=settings.max_gap_fraction,
        stale_feed_s=settings.stale_feed_s,
        horizontals=settings.horizontals,
        partner=partner_cfg,
    )

    source: ReplaySource | SeedLinkSource
    seedlink: SeedLinkSource | None = None
    if args.mode == "replay":
        packets, sr = replay_packets(settings, args)
        print(f"replaying {len(packets)} packets from {settings.station_key} at {sr:g} Hz")
        source = ReplaySource(packets, speed=args.speed)
        live_cfg = LiveConfig(**{**live_cfg.__dict__, "sampling_rate": sr})
    else:
        site = STATION_SITES[settings.station_key]
        extra_streams: list[tuple[Station, str]] = []
        if settings.horizontals:
            for comp in ("N", "E"):
                extra_streams.append(
                    (
                        Station(
                            site.site.network,
                            site.site.station,
                            site.site.location,
                            site.site.channel[:2] + comp,
                        ),
                        horizontal_key(settings.station_key, comp),
                    )
                )
        if settings.partner_key:
            extra_streams.append((STATION_SITES[settings.partner_key].site, settings.partner_key))
        seedlink = SeedLinkSource(
            station=site.site,
            server=settings.server,
            key=settings.station_key,
            extra_streams=tuple(extra_streams),
        )
        source = seedlink
        print(f"connecting to {settings.server} for {settings.station_key}; stop with Ctrl-C")
        if args.hours > 0:
            threading.Timer(args.hours * 3600.0, seedlink.stop).start()

    state = ShadowState(settings, args.mode, stats, health, seedlink, outbox, args.quiet)
    health_server = HealthServer(
        settings.health_port,
        state.snapshot,
        enabled=args.mode == "live" and settings.health_port > 0,
    )
    health_server.start()
    if health_server.running:
        print(f"health      : {health_server.url}")
    state.write_status()

    try:
        outcomes = run_shadow(
            source,
            reach=settings.reach,
            model_version="shadow",
            live=live_cfg,
            stats=stats,
            audit_log=audit,
            health=health,
            on_verdict=state.on_verdict,
            on_outcome=state.on_outcome,
            station_lat=STATION_SITES[settings.station_key].latitude,
            station_lon=STATION_SITES[settings.station_key].longitude,
        )
    except KeyboardInterrupt:
        print("\nstopped by operator")
        outcomes = []
    finally:
        state.write_status()
        health_server.stop()

    summarise(outcomes, stats, health)
    print(f"audit       : {settings.audit_path}")
    print(f"status      : {settings.status_path}")
    if outbox.pending():
        print(f"waiting     : {len(outbox.pending())} staged alert(s); see scripts/outbox.py list")
    return 0


def _replace(settings: SiteSettings, **changes: Any) -> SiteSettings:
    from dataclasses import replace

    return replace(settings, **changes)


if __name__ == "__main__":
    sys.exit(main())
