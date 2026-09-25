"""The real time loop: packets in, decisions out, nothing sent (issue #30).

This is the missing half of the system. Everything downstream of it was already built
and tested against replayed data; what did not exist was anything that consumes a live
feed. The loop here does three things and no more:

1. assemble packets into windows (``ghadi.stream``),
2. run the same detector, features, and classifier the offline path runs,
3. hand each window to ``ghadi.service.process_window`` and record the outcome.

**Shadow only.** A decision is written to the audit log and nothing else. There is no
path from this module to a message leaving the machine: delivery, and the human gate in
front of it, is issue #36. ``run_shadow`` refuses to run with ``shadow=False``.

**It does not claim real time viability.** The seven day latency run (issue #8) is still
open. What this module adds is the measurement: every window carries the worst packet
delay that built it, and ``FeedStats`` accumulates them, so running the loop *is* the
latency run.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np

from .classify import classify_segment
from .config import DEFAULT, GhadiConfig
from .detect import sta_lta
from .features import Features, extract, preprocess
from .service import (
    AuditLog,
    GaugeObservation,
    HealthMonitor,
    ServiceOutcome,
    WindowObservation,
    run_over,
)
from .stream import PacketSource, StreamAssembler, StreamWindow
from .teleseism import Origin

__all__ = [
    "FeedStats",
    "LiveConfig",
    "WindowVerdict",
    "observation_from_window",
    "observations_from_source",
    "run_shadow",
    "windows_from_source",
]


@dataclass(frozen=True)
class LiveConfig:
    """Settings the live loop needs that the offline path never had to state."""

    station: str = "NK.KKN"
    # None means take the rate from the first packet. A live feed states its own rate,
    # and a guess that disagrees with it would reject every packet.
    sampling_rate: float | None = None
    window_s: float = DEFAULT.seismic.window_s
    # Windows overlap so that no arrival falls in the settling part of every window
    # that contains it. With a 240 s window and a 60 s hop, an onset is at least 60 s
    # into some window, and that window still has the whole decision segment after it.
    hop_s: float = 60.0
    grace_s: float = 5.0
    # A window assembled mostly from filled gaps is not evidence either way. Above this
    # share of missing samples the window is reported as unusable rather than decided
    # on, the same refusal the radar side makes when too little of the region is usable.
    max_gap_fraction: float = 0.40
    # A feed this far behind is not real time any more. The loop keeps running and keeps
    # deciding; it flags the window so the operator can see the feed degraded.
    stale_feed_s: float = 120.0


@dataclass
class FeedStats:
    """What the loop saw. Running it long enough is the latency run of issue #8."""

    windows: int = 0
    unusable_windows: int = 0
    triggered_windows: int = 0
    stale_windows: int = 0
    late_packets: int = 0
    delays_s: list[float] = field(default_factory=list)

    def observe(self, window: StreamWindow, *, usable: bool, triggered: bool) -> None:
        self.windows += 1
        if not usable:
            self.unusable_windows += 1
        if triggered:
            self.triggered_windows += 1
        if math.isfinite(window.max_delay_s):
            self.delays_s.append(window.max_delay_s)

    def percentile(self, q: float) -> float:
        if not self.delays_s:
            return float("nan")
        return float(np.percentile(np.asarray(self.delays_s, dtype=float), q))

    def as_dict(self) -> dict[str, float | int]:
        return {
            "windows": self.windows,
            "unusable_windows": self.unusable_windows,
            "triggered_windows": self.triggered_windows,
            "stale_windows": self.stale_windows,
            "late_packets": self.late_packets,
            "delay_p50_s": round(self.percentile(50), 2),
            "delay_p95_s": round(self.percentile(95), 2),
            "delay_max_s": round(max(self.delays_s), 2) if self.delays_s else float("nan"),
        }


@dataclass(frozen=True)
class WindowVerdict:
    """Why a window did or did not become an observation. Nothing is dropped silently."""

    window: StreamWindow
    observation: WindowObservation | None
    reason: str  # "ok", "unusable", "no_trigger", "segment_too_short", "already_decided"
    stale: bool = False


def observation_from_window(
    window: StreamWindow,
    *,
    origins: tuple[Origin, ...] = (),
    gauge: GaugeObservation | None = None,
    event_id: str = "GHADI-LIVE",
    live: LiveConfig | None = None,
    config: GhadiConfig | None = None,
    feed_time: datetime | None = None,
) -> WindowVerdict:
    """Run the detector on one window and build what the service decides from.

    The features are taken from the decision segment after a trigger onset, which is
    what the detector can actually compute when an alert has to fire (exp005). Triggers
    are taken in time order, as they would arrive, and the first whose segment looks
    like a mass movement is the one carried forward. If none does, the first trigger
    is carried forward so the decision records that the window was seen and rejected.
    This is the same basis exp018 measured the false alarm rate on.

    ``feed_time`` is the arrival time of the newest packet. A window that closed long
    before that is stale: still evidence, but late, and flagged as such.
    """
    lcfg = live or LiveConfig()
    cfg = config or DEFAULT
    now = feed_time or datetime.now(tz=UTC)
    stale = (now - window.end_utc).total_seconds() > lcfg.stale_feed_s

    if window.gap_fraction > lcfg.max_gap_fraction:
        return WindowVerdict(window, None, "unusable", stale)

    proc = preprocess(window.data, window.sampling_rate, cfg.seismic)
    detection = sta_lta(proc, window.sampling_rate, config=cfg.seismic, preprocessed=True)
    if not detection.triggers:
        return WindowVerdict(window, None, "no_trigger", stale)

    chosen: tuple[float, Features] | None = None
    for trigger in sorted(detection.triggers, key=lambda t: t.on_s):
        try:
            segment = extract(
                proc,
                window.sampling_rate,
                config=cfg.seismic,
                preprocessed=True,
                onset_s=trigger.on_s,
                segment_s=cfg.seismic.decision_segment_s,
            )
        except ValueError:
            # Too close to the end of the window for a full segment. The next window
            # carries the same energy, so this is a wait, not a loss.
            continue
        if chosen is None:
            chosen = (trigger.on_s, segment)
        like = classify_segment(
            segment.spectral_ratio_low_high, segment.spectral_centroid_hz, config=cfg.classify
        )
        if like.mass_movement_like:
            chosen = (trigger.on_s, segment)
            break
    if chosen is None:
        return WindowVerdict(window, None, "segment_too_short", stale)
    onset_s, segment = chosen

    obs = WindowObservation(
        window_start_utc=window.start_utc,
        detected_utc=window.start_utc + timedelta(seconds=onset_s),
        segment_lf_hf=segment.spectral_ratio_low_high,
        segment_centroid_hz=segment.spectral_centroid_hz,
        seismic_sensor_alive=True,
        gauge=gauge,
        origins=origins,
        event_id=event_id,
    )
    return WindowVerdict(window, obs, "ok", stale)


OnVerdict = Callable[[WindowVerdict], None]


@dataclass
class _FeedTime:
    """The arrival time of the newest packet seen: the loop's idea of now."""

    latest: datetime | None = None

    def advance(self, when: datetime) -> None:
        if self.latest is None or when > self.latest:
            self.latest = when


def windows_from_source(
    source: PacketSource,
    *,
    live: LiveConfig | None = None,
    stats: FeedStats | None = None,
    tracker: _FeedTime | None = None,
) -> Iterator[StreamWindow]:
    """Assemble a packet feed into windows, closing them as the feed moves on.

    Windows are closed against **feed time**, the arrival time of the newest packet
    seen, not the wall clock. On a live feed the two are the same thing. On replayed
    data they are years apart, and using the wall clock there would close every window
    the moment it opened and then treat all its data as late. One rule for both keeps
    the replay path and the live path identical, which is the point of having it.

    A partial window still open when the feed ends is not emitted: half a window is not
    a decision.
    """
    lcfg = live or LiveConfig()
    assembler: StreamAssembler | None = None
    feed = tracker or _FeedTime()
    for packet in source.packets():
        if assembler is None:
            assembler = StreamAssembler(
                window_s=lcfg.window_s,
                sampling_rate=lcfg.sampling_rate or packet.sampling_rate,
                hop_s=lcfg.hop_s,
                grace_s=lcfg.grace_s,
            )
        yield from assembler.push(packet)
        feed.advance(packet.received_utc)
        assert feed.latest is not None
        yield from assembler.flush(feed.latest)
    if assembler is None or feed.latest is None:
        return
    yield from assembler.flush(feed.latest + timedelta(seconds=lcfg.grace_s))
    if stats is not None:
        stats.late_packets += assembler.late_packets


def observations_from_source(
    source: PacketSource,
    *,
    origins: tuple[Origin, ...] = (),
    live: LiveConfig | None = None,
    config: GhadiConfig | None = None,
    stats: FeedStats | None = None,
    on_verdict: OnVerdict | None = None,
) -> Iterator[WindowObservation]:
    """Yield one observation per arrival.

    Overlapping windows see the same arrival several times. Once an onset has produced
    an observation, later windows whose onset falls inside that decision segment are
    reported as ``already_decided`` and not yielded again: the decision has been made
    and may already have reached someone. Windows with no trigger, or with too many
    gaps, are reported through ``on_verdict`` and counted in ``stats``. Nothing is
    discarded without a record.
    """
    lcfg = live or LiveConfig()
    cfg = config or DEFAULT
    tracker = _FeedTime()
    decided_until: datetime | None = None
    for window in windows_from_source(source, live=lcfg, stats=stats, tracker=tracker):
        verdict = observation_from_window(
            window, origins=origins, live=lcfg, config=cfg, feed_time=tracker.latest
        )
        obs = verdict.observation
        if obs is not None and decided_until is not None and obs.detected_utc < decided_until:
            verdict = WindowVerdict(window, None, "already_decided", verdict.stale)
            obs = None
        if obs is not None:
            decided_until = obs.detected_utc + timedelta(seconds=cfg.seismic.decision_segment_s)
        if stats is not None:
            stats.observe(window, usable=verdict.reason != "unusable", triggered=obs is not None)
            if verdict.stale:
                stats.stale_windows += 1
        if on_verdict is not None:
            on_verdict(verdict)
        if obs is not None:
            yield obs


def run_shadow(
    source: PacketSource,
    *,
    reach: str,
    model_version: str,
    shadow: bool = True,
    origins: tuple[Origin, ...] = (),
    live: LiveConfig | None = None,
    config: GhadiConfig | None = None,
    stats: FeedStats | None = None,
    on_verdict: OnVerdict | None = None,
    audit_log: AuditLog | None = None,
    health: HealthMonitor | None = None,
    warning_latency_s: float | None = None,
) -> list[ServiceOutcome]:
    """Drive the live feed through the tested pipeline, in shadow mode only.

    Shadow means what tier T0 in the handoff means: the system decides, the decision is
    recorded, and nothing leaves the machine. There is no argument that turns this into
    a public alerting path, because the delivery layer and the human gate in front of it
    do not exist yet (issue #36).
    """
    if not shadow:
        raise ValueError(
            "run_shadow is shadow only. Delivering an alert to anyone is issue #36, and "
            "promotion past shadow needs a completed monsoon of shadow operation "
            "(handoff section 9)."
        )
    observations = observations_from_source(
        source,
        origins=origins,
        live=live,
        config=config,
        stats=stats,
        on_verdict=on_verdict,
    )
    return run_over(
        observations,
        reach=reach,
        model_version=model_version,
        audit_log=audit_log,
        health=health,
        warning_latency_s=warning_latency_s,
        config=config,
    )
