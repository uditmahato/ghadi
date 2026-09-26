"""The real time loop: packets in, decisions out, nothing sent (issues #30, #31, #37).

This is the missing half of the system. Everything downstream of it was already built
and tested against replayed data; what did not exist was anything that consumes a live
feed. The loop here does three things and no more:

1. assemble packets into windows (``ghadi.stream``),
2. run the same detector, features, and classifier the offline path runs,
3. hand each window to ``ghadi.service`` and record the outcome.

Two optional inputs make the seismic channel harder to fool, and both are measured
before they are trusted:

* **Horizontal channels.** When the feed carries the station's N and E components, the
  horizontal to vertical energy ratio over the decision segment is computed and passed
  to the classifier (exp021). The rule itself is off until ``ClassifyConfig`` turns it
  on with a margin from exp022.
* **A partner station.** When a second station's feed is present, its trigger onsets
  are kept, and a mass movement like onset at the primary station is *corroborated*
  when the partner triggered at a time that fits a source in the region (exp019).
  Corroboration raises the seismic channel and never becomes a second independence
  group. If the partner's window closes after the primary decision was made, the
  decision is issued again once, marked corroborated, so the record shows the upgrade.

**Shadow only.** A decision is written to the audit log and nothing else. There is no
path from this module to a message leaving the machine: delivery, and the human gate in
front of it, live in ``ghadi.delivery``. ``run_shadow`` refuses to run with
``shadow=False``.

**It does not claim real time viability.** Every window carries the worst packet delay
that built it, and ``FeedStats`` accumulates them, so running the loop *is* the latency
run of issue #8.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import numpy as np

from .associate import Pick, SearchRegion, arrival_bracket
from .classify import classify_segment
from .config import DEFAULT, GhadiConfig
from .detect import sta_lta
from .features import Features, extract, preprocess
from .features_3c import hv_ratio
from .service import (
    AuditLog,
    GaugeObservation,
    HealthMonitor,
    ServiceOutcome,
    WindowObservation,
    run_over_each,
)
from .stream import PacketSource, StreamAssembler, StreamWindow
from .teleseism import Origin

__all__ = [
    "FeedStats",
    "LiveConfig",
    "PartnerConfig",
    "WindowVerdict",
    "horizontal_key",
    "observation_from_window",
    "observations_from_source",
    "run_shadow",
    "windows_from_source",
]

DEFAULT_REGION = SearchRegion(27.4, 29.0, 84.6, 86.6, step_km=4.0)


def horizontal_key(station: str, component: str) -> str:
    """The packet key a station's horizontal component travels under."""
    return f"{station}:{component}"


@dataclass(frozen=True)
class PartnerConfig:
    """A second station whose triggers corroborate the primary one (issue #31)."""

    key: str
    lat: float
    lon: float
    region: SearchRegion = DEFAULT_REGION
    keep_s: float = 1800.0  # how long partner triggers are remembered
    upgrade_s: float = 600.0  # how long an uncorroborated decision can still be upgraded


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
    # Whether the feed carries the primary station's horizontal components under
    # ``horizontal_key``. When True the loop waits, up to one hop, for the horizontals
    # of a window before deciding on it.
    horizontals: bool = False
    partner: PartnerConfig | None = None


@dataclass
class FeedStats:
    """What the loop saw. Running it long enough is the latency run of issue #8."""

    windows: int = 0
    unusable_windows: int = 0
    triggered_windows: int = 0
    stale_windows: int = 0
    late_packets: int = 0
    corroborated: int = 0
    upgrades: int = 0
    horizontals_missing: int = 0
    delays_s: list[float] = field(default_factory=list)
    # Seconds from the picked onset to the moment the decision could be made: the end
    # of the window that held the full decision segment, plus the feed delay.
    decision_latencies_s: list[float] = field(default_factory=list)

    def observe(self, window: StreamWindow, *, usable: bool, triggered: bool) -> None:
        self.windows += 1
        if not usable:
            self.unusable_windows += 1
        if triggered:
            self.triggered_windows += 1
        if math.isfinite(window.max_delay_s):
            self.delays_s.append(window.max_delay_s)

    def note_decision(self, window: StreamWindow, detected_utc: datetime) -> None:
        delay = window.max_delay_s if math.isfinite(window.max_delay_s) else 0.0
        self.decision_latencies_s.append(
            (window.end_utc - detected_utc).total_seconds() + max(delay, 0.0)
        )

    def percentile(self, q: float) -> float:
        if not self.delays_s:
            return float("nan")
        return float(np.percentile(np.asarray(self.delays_s, dtype=float), q))

    def decision_percentile(self, q: float) -> float:
        if not self.decision_latencies_s:
            return float("nan")
        return float(np.percentile(np.asarray(self.decision_latencies_s, dtype=float), q))

    def as_dict(self) -> dict[str, float | int]:
        return {
            "windows": self.windows,
            "unusable_windows": self.unusable_windows,
            "triggered_windows": self.triggered_windows,
            "stale_windows": self.stale_windows,
            "late_packets": self.late_packets,
            "corroborated": self.corroborated,
            "upgrades": self.upgrades,
            "horizontals_missing": self.horizontals_missing,
            "delay_p50_s": round(self.percentile(50), 2),
            "delay_p95_s": round(self.percentile(95), 2),
            "delay_max_s": round(max(self.delays_s), 2) if self.delays_s else float("nan"),
            "decision_latency_p50_s": round(self.decision_percentile(50), 1),
            "decision_latency_max_s": round(max(self.decision_latencies_s), 1)
            if self.decision_latencies_s
            else float("nan"),
        }


@dataclass(frozen=True)
class WindowVerdict:
    """Why a window did or did not become an observation. Nothing is dropped silently."""

    window: StreamWindow
    observation: WindowObservation | None
    # "ok", "unusable", "no_trigger", "segment_too_short", "gap_edge",
    # "already_decided", "upgraded", "partner"
    reason: str
    stale: bool = False


def on_gap_edge(window: StreamWindow, onset_s: float, settle_s: float) -> bool:
    """True when a filled gap ends inside the settling time before this onset.

    Zero filling a gap makes a step where real data resumes, and a step is exactly what
    a short over long average detector fires on. Such a trigger is an artefact of the
    feed, not an arrival, and is skipped with the reason recorded.
    """
    if window.filled is None:
        return False
    sr = window.sampling_rate
    stop = min(max(round(onset_s * sr), 0), window.filled.size)
    start = max(stop - round(settle_s * sr), 0)
    return bool(window.filled[start:stop].any())


def _segment_hv(
    horizontals: tuple[np.ndarray, np.ndarray] | None,
    proc_z: np.ndarray,
    sampling_rate: float,
    onset_s: float,
    segment_s: float,
    config: GhadiConfig,
) -> float | None:
    if horizontals is None:
        return None
    n, e = horizontals
    m = min(proc_z.size, n.size, e.size)
    a = max(round(onset_s * sampling_rate), 0)
    b = min(a + round(segment_s * sampling_rate), m)
    if b - a < 2:
        return None
    pn = preprocess(n[:m], sampling_rate, config.seismic)
    pe = preprocess(e[:m], sampling_rate, config.seismic)
    value = hv_ratio(proc_z[a:b], pn[a:b], pe[a:b])
    return float(value) if math.isfinite(value) else None


def observation_from_window(
    window: StreamWindow,
    *,
    origins: tuple[Origin, ...] = (),
    gauge: GaugeObservation | None = None,
    event_id: str = "GHADI-LIVE",
    live: LiveConfig | None = None,
    config: GhadiConfig | None = None,
    feed_time: datetime | None = None,
    horizontals: tuple[np.ndarray, np.ndarray] | None = None,
    corroborated_by: Callable[[datetime], bool] | None = None,
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

    chosen: tuple[float, Features, float | None] | None = None
    window_len_s = window.data.size / window.sampling_rate
    segment_s = cfg.seismic.decision_segment_s
    for trigger in sorted(detection.triggers, key=lambda t: t.on_s):
        if on_gap_edge(window, trigger.on_s, cfg.seismic.lta_s):
            continue
        if trigger.on_s + segment_s > window_len_s:
            # The whole decision segment must be inside the window, or the features are
            # computed on a shorter piece than every threshold was set on. A later,
            # overlapping window will hold the full segment.
            continue
        try:
            segment = extract(
                proc,
                window.sampling_rate,
                config=cfg.seismic,
                preprocessed=True,
                onset_s=trigger.on_s,
                segment_s=segment_s,
            )
        except ValueError:
            continue
        hv = _segment_hv(horizontals, proc, window.sampling_rate, trigger.on_s, segment_s, cfg)
        if chosen is None:
            chosen = (trigger.on_s, segment, hv)
        like = classify_segment(
            segment.spectral_ratio_low_high,
            segment.spectral_centroid_hz,
            config=cfg.classify,
            segment_hv=hv,
        )
        if like.mass_movement_like:
            chosen = (trigger.on_s, segment, hv)
            break
    if chosen is None:
        reason = "segment_too_short"
        if all(on_gap_edge(window, tr.on_s, cfg.seismic.lta_s) for tr in detection.triggers):
            reason = "gap_edge"
        return WindowVerdict(window, None, reason, stale)
    onset_s, segment, hv = chosen
    detected = window.start_utc + timedelta(seconds=onset_s)

    obs = WindowObservation(
        window_start_utc=window.start_utc,
        detected_utc=detected,
        segment_lf_hf=segment.spectral_ratio_low_high,
        segment_centroid_hz=segment.spectral_centroid_hz,
        seismic_sensor_alive=True,
        gauge=gauge,
        origins=origins,
        event_id=event_id,
        segment_hv=hv,
        seismic_corroborated=bool(corroborated_by(detected)) if corroborated_by else False,
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
            # Each station takes its own rate from its first packet. A rate given in
            # the configuration is a check on the primary station, not a setting for
            # every station on the feed.
            assembler = StreamAssembler(
                window_s=lcfg.window_s, sampling_rate=None, hop_s=lcfg.hop_s, grace_s=lcfg.grace_s
            )
        if (
            packet.station == lcfg.station
            and lcfg.sampling_rate is not None
            and abs(packet.sampling_rate - lcfg.sampling_rate) > 1e-9
        ):
            continue  # a primary packet at the wrong rate is rejected, not resampled
        yield from assembler.push(packet)
        feed.advance(packet.received_utc)
        assert feed.latest is not None
        yield from assembler.flush(feed.latest)
    if assembler is None or feed.latest is None:
        return
    yield from assembler.flush(feed.latest + timedelta(seconds=lcfg.grace_s))
    if stats is not None:
        stats.late_packets += assembler.late_packets


@dataclass
class _Partner:
    """Trigger onsets seen at the partner station, and the corroboration test."""

    config: PartnerConfig
    station_lat: float
    station_lon: float
    onsets: deque[datetime] = field(default_factory=deque)

    def add_window(self, window: StreamWindow, cfg: GhadiConfig, max_gap: float) -> int:
        if window.gap_fraction > max_gap:
            return 0
        proc = preprocess(window.data, window.sampling_rate, cfg.seismic)
        detection = sta_lta(proc, window.sampling_rate, config=cfg.seismic, preprocessed=True)
        added = 0
        for trigger in detection.triggers:
            if on_gap_edge(window, trigger.on_s, cfg.seismic.lta_s):
                continue
            when = window.start_utc + timedelta(seconds=trigger.on_s)
            if all(abs((when - o).total_seconds()) > 1.0 for o in self.onsets):
                self.onsets.append(when)
                added += 1
        cutoff = window.end_utc - timedelta(seconds=self.config.keep_s)
        while self.onsets and self.onsets[0] < cutoff:
            self.onsets.popleft()
        return added

    def corroborates(self, detected_utc: datetime, primary_key: str) -> bool:
        pick = Pick(primary_key, self.station_lat, self.station_lon, detected_utc)
        lo, hi = arrival_bracket(pick, self.config.lat, self.config.lon, self.config.region)
        return any(lo <= o <= hi for o in self.onsets)


def observations_from_source(
    source: PacketSource,
    *,
    origins: tuple[Origin, ...] = (),
    live: LiveConfig | None = None,
    config: GhadiConfig | None = None,
    stats: FeedStats | None = None,
    on_verdict: OnVerdict | None = None,
    station_lat: float | None = None,
    station_lon: float | None = None,
) -> Iterator[WindowObservation]:
    """Yield one observation per arrival.

    Overlapping windows see the same arrival several times. Once an onset has produced
    an observation, later windows whose onset falls inside that decision segment are
    reported as ``already_decided`` and not yielded again: the decision has been made
    and may already have reached someone. The one exception is an upgrade: a partner
    station's trigger arriving later that fits the onset yields the same observation
    once more, marked corroborated. Windows with no trigger, or with too many gaps, are
    reported through ``on_verdict`` and counted in ``stats``. Nothing is discarded
    without a record.
    """
    lcfg = live or LiveConfig()
    cfg = config or DEFAULT
    tracker = _FeedTime()
    decided_until: datetime | None = None
    partner: _Partner | None = None
    if lcfg.partner is not None:
        if station_lat is None or station_lon is None:
            raise ValueError("a partner station needs the primary station's coordinates")
        partner = _Partner(lcfg.partner, station_lat, station_lon)
    # Decisions made without corroboration that a later partner trigger may upgrade.
    pending_upgrade: list[tuple[WindowObservation, StreamWindow]] = []
    # Windows waiting for their horizontals, keyed by start time.
    waiting: dict[datetime, dict[str, StreamWindow]] = {}
    h_keys = {horizontal_key(lcfg.station, "N"): "N", horizontal_key(lcfg.station, "E"): "E"}

    def decide(
        window: StreamWindow, horizontals: tuple[np.ndarray, np.ndarray] | None
    ) -> Iterator[WindowObservation]:
        nonlocal decided_until
        verdict = observation_from_window(
            window,
            origins=origins,
            live=lcfg,
            config=cfg,
            feed_time=tracker.latest,
            horizontals=horizontals,
            corroborated_by=(
                (lambda when: partner.corroborates(when, lcfg.station)) if partner else None
            ),
        )
        obs = verdict.observation
        if obs is not None and decided_until is not None and obs.detected_utc < decided_until:
            verdict = WindowVerdict(window, None, "already_decided", verdict.stale)
            obs = None
        if obs is not None:
            decided_until = obs.detected_utc + timedelta(seconds=cfg.seismic.decision_segment_s)
            if partner is not None and not obs.seismic_corroborated:
                pending_upgrade.append((obs, window))
            elif obs.seismic_corroborated and stats is not None:
                stats.corroborated += 1
        if stats is not None:
            stats.observe(window, usable=verdict.reason != "unusable", triggered=obs is not None)
            if verdict.stale:
                stats.stale_windows += 1
            if obs is not None:
                stats.note_decision(window, obs.detected_utc)
                if lcfg.horizontals and horizontals is None:
                    stats.horizontals_missing += 1
        if on_verdict is not None:
            on_verdict(verdict)
        if obs is not None:
            yield obs

    def upgrades(window: StreamWindow) -> Iterator[WindowObservation]:
        """Re-issue uncorroborated decisions a new partner trigger now fits."""
        assert partner is not None
        keep: list[tuple[WindowObservation, StreamWindow]] = []
        for obs, primary_window in pending_upgrade:
            age = (window.end_utc - obs.detected_utc).total_seconds()
            if age > lcfg.partner.upgrade_s if lcfg.partner else False:
                continue
            if partner.corroborates(obs.detected_utc, lcfg.station):
                upgraded = replace(obs, seismic_corroborated=True)
                if stats is not None:
                    stats.corroborated += 1
                    stats.upgrades += 1
                if on_verdict is not None:
                    on_verdict(WindowVerdict(primary_window, upgraded, "upgraded"))
                yield upgraded
            else:
                keep.append((obs, primary_window))
        pending_upgrade[:] = keep

    def release_waiting(before: datetime) -> Iterator[WindowObservation]:
        """Decide on primary windows whose horizontals never came, once they are old."""
        for start in sorted(waiting):
            group = waiting[start]
            if "Z" in group and start + timedelta(seconds=lcfg.window_s + lcfg.hop_s) <= before:
                z = waiting.pop(start)["Z"]
                yield from decide(z, None)

    for window in windows_from_source(source, live=lcfg, stats=stats, tracker=tracker):
        if partner is not None and window.station == partner.config.key:
            if partner.add_window(window, cfg, lcfg.max_gap_fraction):
                yield from upgrades(window)
            if on_verdict is not None:
                on_verdict(WindowVerdict(window, None, "partner"))
            continue
        if window.station in h_keys or (lcfg.horizontals and window.station == lcfg.station):
            comp = h_keys.get(window.station, "Z")
            group = waiting.setdefault(window.start_utc, {})
            group[comp] = window
            if {"Z", "N", "E"} <= set(group):
                waiting.pop(window.start_utc)
                yield from decide(group["Z"], (group["N"].data, group["E"].data))
            if tracker.latest is not None:
                yield from release_waiting(tracker.latest)
            continue
        if window.station != lcfg.station:
            continue
        yield from decide(window, None)
    if tracker.latest is not None:
        yield from release_waiting(tracker.latest + timedelta(days=1))


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
    station_lat: float | None = None,
    station_lon: float | None = None,
    on_outcome: Callable[[ServiceOutcome], None] | None = None,
) -> list[ServiceOutcome]:
    """Drive the live feed through the tested pipeline, in shadow mode only.

    Shadow means what tier T0 in the handoff means: the system decides, the decision is
    recorded, and nothing leaves the machine. There is no argument that turns this into
    a public alerting path; delivery and the human gate in front of it are a separate
    module that needs a named person.
    """
    if not shadow:
        raise ValueError(
            "run_shadow is shadow only. Delivering an alert to anyone needs the human "
            "gate in ghadi.delivery, and promotion past shadow needs a completed monsoon "
            "of shadow operation (handoff section 9)."
        )
    observations = observations_from_source(
        source,
        origins=origins,
        live=live,
        config=config,
        stats=stats,
        on_verdict=on_verdict,
        station_lat=station_lat,
        station_lon=station_lon,
    )
    extra: dict[str, float] = {}
    if station_lat is not None and station_lon is not None:
        extra = {"station_lat": station_lat, "station_lon": station_lon}
    outcomes: list[ServiceOutcome] = []
    for outcome in run_over_each(
        observations,
        reach=reach,
        model_version=model_version,
        audit_log=audit_log,
        health=health,
        warning_latency_s=warning_latency_s,
        config=config,
        **extra,
    ):
        outcomes.append(outcome)
        if on_outcome is not None:
            on_outcome(outcome)
    return outcomes
