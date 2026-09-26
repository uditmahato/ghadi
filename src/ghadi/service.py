"""The orchestration layer that makes the pieces one pipeline (M5).

Everything upstream of this module detects, classifies, or measures one thing. This is
where a window becomes a decision: the seismic classification and the gauge anomaly are
turned into fusion channels, a distant earthquake is subtracted, the channels are fused,
the lead time is computed, and — if the decision clears the bar — a CAP alert is built.
Every decision is written to an append-only, hash-chained audit log, because after a
false alarm or a missed event the question is always "what did the system see, and
why did it act", and a decision that cannot answer that is not accountable.

**What is complete here.** The pipeline runs end to end and is exercised offline by a
replay driver (`run_over`). Given a window's observations it produces the same decision,
alert and audit record a live loop would.

**What is deliberately not here.** The live SeedLink/DHM feed. `run_forever` does not
fabricate one — it raises, pointing at the go/no-go this project has not closed: the
seven-day real-time latency run (issue 0.1). The 3.4-hour probe (docs/LATENCY.md) is
encouraging but is not that run, and until it exists the loop must not present itself as
operational. The input is a seam: `run_over` consumes any iterable of observations, so
the live source is a driver swapped in at the top, exactly as `ghadi.dhm` is for gauges.

No alert this module emits is `Actual`/`Public`: that requires an authorised build
(`ghadi.cap`), which requires an alerting authority to have signed off.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from .alerting import build_alert_context
from .cap import build_cap, to_xml
from .classify import classify_segment
from .config import (
    DEFAULT,
    PRIMARY_STATION_LAT,
    PRIMARY_STATION_LON,
    GhadiConfig,
)
from .fusion import Channel, Decision, Tier, channel_from_hydro, channel_from_seismic, fuse
from .hydro import detect_anomaly
from .teleseism import Origin, Suppression, explain
from .travel import get_reach


@dataclass(frozen=True)
class GaugeObservation:
    """A downstream gauge series for one window, already ingested and liveness-assessed."""

    times_s: Sequence[float]
    stage_m: Sequence[float]
    sensor_alive: bool
    name: str = "gauge"


@dataclass(frozen=True)
class WindowObservation:
    """Everything one decision is made from. Structured, so no free text reaches CAP.

    The seismic side is the two decision-segment spectral features plus the trigger's
    onset time (used to ask the global catalogue whether a distant earthquake explains
    it). Feature extraction from the raw waveform is the detector's job upstream; this
    layer orchestrates, it does not re-run signal processing.
    """

    window_start_utc: datetime
    detected_utc: datetime  # onset time of the seismic trigger, timezone-aware UTC
    segment_lf_hf: float
    segment_centroid_hz: float
    seismic_sensor_alive: bool = True
    gauge: GaugeObservation | None = None
    origins: tuple[Origin, ...] = ()  # rolling global M>=5.5 catalogue for suppression
    event_id: str = "GHADI-EVENT"
    # Horizontal to vertical energy over the decision segment, when the horizontals
    # were available (issue #37). None means the H/V rule cannot be applied.
    segment_hv: float | None = None
    # A second station saw this onset at a time fitting a source in the region (#31).
    seismic_corroborated: bool = False


@dataclass(frozen=True)
class ServiceOutcome:
    """A single decision, everything that produced it, and the alert if one was raised."""

    decision: Decision
    suppression: Suppression
    channels: tuple[Channel, ...]
    alert_xml: str | None  # None when no alert is raised (tier NONE, or suppressed)
    lead_times_min: dict[str, float] | None
    audit: AuditRecord


# --------------------------------------------------------------------------------------
# The per-window decision.
# --------------------------------------------------------------------------------------
def process_window(
    obs: WindowObservation,
    reach: str,
    model_version: str,
    *,
    station_lat: float = PRIMARY_STATION_LAT,
    station_lon: float = PRIMARY_STATION_LON,
    warning_latency_s: float | None = None,
    prev_hash: str = "",
    config: GhadiConfig | None = None,
) -> ServiceOutcome:
    """Turn one window's observations into a decision, an alert, and an audit record.

    The order matters and is the architecture: classify the seismic window, subtract a
    distant earthquake if the global catalogue explains the onset, add the independent
    gauge channel, fuse, then — only if the fused decision clears its tier — attach the
    lead time and build the alert.
    """
    cfg = config or DEFAULT

    classification = classify_segment(
        obs.segment_lf_hf,
        obs.segment_centroid_hz,
        config=cfg.classify,
        segment_hv=obs.segment_hv,
    )
    suppression = explain(obs.detected_utc, obs.origins, station_lat, station_lon)

    channels: list[Channel] = []
    # A low-frequency window explained by a distant earthquake is not evidence of a local
    # mass movement. Suppression neutralises the seismic channel to quiet — it never
    # touches the independent gauge, which a teleseism cannot fake.
    if suppression.suppressed:
        channels.append(
            Channel(
                name="seismic",
                probability=cfg.fusion.seismic_quiet_p,
                independence_group="upstream_seismic",
                alive=obs.seismic_sensor_alive,
                detail=f"suppressed as teleseism: {suppression.reason}",
            )
        )
    else:
        channels.append(
            channel_from_seismic(
                classification,
                sensor_alive=obs.seismic_sensor_alive,
                config=cfg.fusion,
                corroborated=obs.seismic_corroborated,
            )
        )

    if obs.gauge is not None:
        anomaly = detect_anomaly(
            np.asarray(obs.gauge.times_s, dtype=float),
            np.asarray(obs.gauge.stage_m, dtype=float),
            config=cfg.hydro,
        )
        channels.append(
            channel_from_hydro(
                anomaly,
                sensor_alive=obs.gauge.sensor_alive,
                name=obs.gauge.name,
                config=cfg.fusion,
            )
        )

    decision = fuse(channels, config=cfg.fusion)

    alert_xml: str | None = None
    lead_times_min: dict[str, float] | None = None
    if decision.tier is not Tier.NONE:
        context = build_alert_context(
            event_id=obs.event_id,
            detected_utc=obs.detected_utc,
            reach=reach,
            model_version=model_version,
            warning_latency_s=warning_latency_s,
            config=cfg.travel,
        )
        lead_times_min = context.lead_times_min
        alert = build_cap(decision, context, config=cfg.cap)
        alert_xml = to_xml(alert)

    audit = AuditRecord.build(
        obs=obs,
        reach=get_reach(reach).reach_id,
        model_version=model_version,
        classification_like=classification.mass_movement_like,
        suppression=suppression,
        decision=decision,
        alert_xml=alert_xml,
        lead_times_min=lead_times_min,
        prev_hash=prev_hash,
    )

    return ServiceOutcome(
        decision=decision,
        suppression=suppression,
        channels=tuple(channels),
        alert_xml=alert_xml,
        lead_times_min=lead_times_min,
        audit=audit,
    )


# --------------------------------------------------------------------------------------
# The append-only, hash-chained audit log.
# --------------------------------------------------------------------------------------
def _canonical(payload: dict[str, object]) -> str:
    """Deterministic JSON so a record hashes to the same value everywhere."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class AuditRecord:
    """One immutable decision record, chained to the previous by hash.

    The chain is what makes the log tamper-evident: altering any past record changes its
    hash, which breaks every ``prev_hash`` after it. ``verify_chain`` detects exactly
    that. This is the artefact that protects the operator after the fact — and, given the
    DRRM Regulations' language about not causing "unnecessary panic", the record that
    shows a suppressed alert was a reasoned decision, not a missed event.
    """

    payload: dict[str, object]
    prev_hash: str
    record_hash: str

    @staticmethod
    def build(
        *,
        obs: WindowObservation,
        reach: str,
        model_version: str,
        classification_like: bool,
        suppression: Suppression,
        decision: Decision,
        alert_xml: str | None,
        lead_times_min: dict[str, float] | None,
        prev_hash: str,
    ) -> AuditRecord:
        payload: dict[str, object] = {
            "window_start_utc": obs.window_start_utc.isoformat(),
            "detected_utc": obs.detected_utc.isoformat(),
            "event_id": obs.event_id,
            "reach": reach,
            "model_version": model_version,
            "seismic": {
                "segment_lf_hf": obs.segment_lf_hf,
                "segment_centroid_hz": obs.segment_centroid_hz,
                "segment_hv": obs.segment_hv,
                "corroborated": obs.seismic_corroborated,
                "mass_movement_like": classification_like,
                "sensor_alive": obs.seismic_sensor_alive,
                "suppressed": suppression.suppressed,
                "suppression_reason": suppression.reason,
            },
            "hydro_present": obs.gauge is not None,
            "decision": {
                "tier": decision.tier.value,
                "probability": round(decision.probability, 6),
                "channels_alive": list(decision.channels_alive),
                "channels_dead": list(decision.channels_dead),
                "independent_groups": decision.independent_groups,
                "rationale": decision.rationale,
            },
            "lead_times_min": lead_times_min,
            "alert_raised": alert_xml is not None,
            # The alert is hashed, not stored: the audit proves what was sent without
            # duplicating it, and a changed alert body breaks the chain.
            "alert_sha256": hashlib.sha256(alert_xml.encode()).hexdigest()
            if alert_xml is not None
            else None,
        }
        canonical = _canonical(payload)
        record_hash = hashlib.sha256((prev_hash + canonical).encode()).hexdigest()
        return AuditRecord(payload=payload, prev_hash=prev_hash, record_hash=record_hash)

    def to_json(self) -> str:
        return _canonical(
            {"payload": self.payload, "prev_hash": self.prev_hash, "record_hash": self.record_hash}
        )


class AuditLog:
    """Append-only writer over a JSONL file, maintaining the hash chain."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.last_hash = self._recover_last_hash()

    def _recover_last_hash(self) -> str:
        if not self.path.exists():
            return ""
        last = ""
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = json.loads(line)["record_hash"]
        return last

    def append(self, record: AuditRecord) -> None:
        """Append a record. Its ``prev_hash`` must match the log's current head."""
        if record.prev_hash != self.last_hash:
            raise ValueError(
                "audit chain break: record.prev_hash does not match the log head — "
                "records must be built against the current head_hash and appended in order"
            )
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")
        self.last_hash = record.record_hash

    @property
    def head_hash(self) -> str:
        return self.last_hash


def verify_chain(path: str | Path) -> bool:
    """Recompute the whole chain from disk; True iff every link is intact."""
    p = Path(path)
    if not p.exists():
        return True  # an empty log is a valid (trivial) chain
    prev = ""
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["prev_hash"] != prev:
            return False
        recomputed = hashlib.sha256((prev + _canonical(entry["payload"])).encode()).hexdigest()
        if recomputed != entry["record_hash"]:
            return False
        prev = entry["record_hash"]
    return True


# --------------------------------------------------------------------------------------
# Health, and the loop.
# --------------------------------------------------------------------------------------
@dataclass
class HealthMonitor:
    """Rolling view of what the system can currently see. Degradation is never silent."""

    windows_seen: int = 0
    alerts_raised: int = 0
    suppressed: int = 0
    last_detected_utc: str | None = None  # isoformat of the most recent window's onset
    last_channels_alive: tuple[str, ...] = ()
    last_channels_dead: tuple[str, ...] = ()

    def observe(self, outcome: ServiceOutcome) -> None:
        self.windows_seen += 1
        if outcome.alert_xml is not None:
            self.alerts_raised += 1
        if outcome.suppression.suppressed:
            self.suppressed += 1
        detected = outcome.audit.payload.get("detected_utc")
        self.last_detected_utc = detected if isinstance(detected, str) else None
        self.last_channels_alive = outcome.decision.channels_alive
        self.last_channels_dead = outcome.decision.channels_dead

    @property
    def blind(self) -> bool:
        """True when the last decision had no live channel — the system is blind."""
        return self.windows_seen > 0 and not self.last_channels_alive


def run_over(
    observations: Iterable[WindowObservation],
    reach: str,
    model_version: str,
    *,
    audit_log: AuditLog | None = None,
    health: HealthMonitor | None = None,
    station_lat: float = PRIMARY_STATION_LAT,
    station_lon: float = PRIMARY_STATION_LON,
    warning_latency_s: float | None = None,
    config: GhadiConfig | None = None,
) -> list[ServiceOutcome]:
    """Drive the pipeline over any iterable of observations — the tested workhorse.

    The live loop and the offline replay differ only in what feeds this: a SeedLink
    source, or a list. Chaining is maintained across the run, so the audit log stays
    verifiable whether it is a replay or a month of real windows.
    """
    return list(
        run_over_each(
            observations,
            reach=reach,
            model_version=model_version,
            audit_log=audit_log,
            health=health,
            station_lat=station_lat,
            station_lon=station_lon,
            warning_latency_s=warning_latency_s,
            config=config,
        )
    )


def run_over_each(
    observations: Iterable[WindowObservation],
    reach: str,
    model_version: str,
    *,
    audit_log: AuditLog | None = None,
    health: HealthMonitor | None = None,
    station_lat: float = PRIMARY_STATION_LAT,
    station_lon: float = PRIMARY_STATION_LON,
    warning_latency_s: float | None = None,
    config: GhadiConfig | None = None,
) -> Iterator[ServiceOutcome]:
    """``run_over`` as a generator, so a live loop can act on each decision as it lands."""
    head = audit_log.head_hash if audit_log is not None else ""
    for obs in observations:
        outcome = process_window(
            obs,
            reach=reach,
            model_version=model_version,
            station_lat=station_lat,
            station_lon=station_lon,
            warning_latency_s=warning_latency_s,
            prev_hash=head,
            config=config,
        )
        if audit_log is not None:
            audit_log.append(outcome.audit)
        head = outcome.audit.record_hash
        if health is not None:
            health.observe(outcome)
        yield outcome


def run_forever(
    *,
    reach: str = "TRISHULI-R07",
    model_version: str = "shadow",
    server: str | None = None,
    audit_path: str | Path | None = None,
    shadow: bool = True,
    config: GhadiConfig | None = None,
) -> None:
    """Run the real-time loop against the live SeedLink feed, in shadow mode.

    Shadow means the system decides, the decision is recorded, and nothing leaves the
    machine (handoff tier T0). Two things this does **not** claim:

    * that real time operation is viable. The seven day latency run (issue #8) is still
      open. Running this loop is what measures it: every window carries the worst packet
      delay that built it, and the feed statistics are printed when the loop ends.
    * that an alert can reach anyone. There is no delivery path in the codebase, by
      design, until issue #36 builds one with a human gate in front of it.

    Args:
        shadow: must stay True. It exists so that the refusal is explicit and testable,
            not so that it can be switched off.
    """
    from .live import FeedStats, LiveConfig, run_shadow
    from .sources import DEFAULT_SEEDLINK_SERVER, SeedLinkSource

    source = SeedLinkSource(server=server or DEFAULT_SEEDLINK_SERVER)
    stats = FeedStats()
    log = AuditLog(Path(audit_path)) if audit_path is not None else None
    health = HealthMonitor()
    try:
        run_shadow(
            source,
            reach=reach,
            model_version=model_version,
            shadow=shadow,
            live=LiveConfig(station=source.station_key),
            config=config,
            stats=stats,
            audit_log=log,
            health=health,
        )
    finally:
        print(f"feed: {stats.as_dict()}", flush=True)
        print(f"reconnections: {source.reconnections}", flush=True)
