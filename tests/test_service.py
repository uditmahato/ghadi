"""The orchestration pipeline: fuse, suppress, alert, and the tamper-evident audit log."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ghadi.hydro import synthetic_surge
from ghadi.service import (
    AuditLog,
    GaugeObservation,
    HealthMonitor,
    WindowObservation,
    process_window,
    run_forever,
    run_over,
    verify_chain,
)
from ghadi.teleseism import Origin

REACH = "TRISHULI-R07"
MODEL = "sta_lta@v0.1.0+classify@v0.1.0"
CASCADE_LF_HF = 4.9188
CASCADE_CENTROID = 1.8852
EQ_LF_HF = 1.66
EQ_CENTROID = 3.04
BASE = datetime(2026, 8, 26, 2, 52, 24, tzinfo=UTC)


def _obs(**kw: object) -> WindowObservation:
    base: dict[str, object] = dict(
        window_start_utc=BASE - timedelta(seconds=120),
        detected_utc=BASE,
        segment_lf_hf=CASCADE_LF_HF,
        segment_centroid_hz=CASCADE_CENTROID,
    )
    base.update(kw)
    return WindowObservation(**base)  # type: ignore[arg-type]


def _gauge(**kw: object) -> GaugeObservation:
    times, stage = synthetic_surge()
    return GaugeObservation(
        times_s=times.tolist(), stage_m=stage.tolist(), sensor_alive=True, **kw  # type: ignore[arg-type]
    )


def test_seismic_and_gauge_together_reach_a_warning_with_lead_times() -> None:
    outcome = process_window(_obs(gauge=_gauge()), reach=REACH, model_version=MODEL)
    assert outcome.decision.tier.value == "WARNING"
    assert outcome.alert_xml is not None
    assert "37 minutes of warning" in outcome.alert_xml  # Bidur at the 60 s default
    assert outcome.lead_times_min is not None


def test_teleseism_suppresses_the_seismic_channel() -> None:
    # A catalogued M6.5 whose P-to-surface window contains the onset explains it.
    origin = Origin(time_utc=BASE, latitude=27.800, longitude=85.279, magnitude=6.5, place="test")
    outcome = process_window(_obs(origins=(origin,)), reach=REACH, model_version=MODEL)
    assert outcome.suppression.suppressed
    # Seismic-only, suppressed, no gauge => nothing to alert on.
    assert outcome.decision.tier.value == "NONE"
    assert outcome.alert_xml is None


def test_suppressed_seismic_but_a_real_gauge_surge_still_alerts() -> None:
    # The independent gauge is not fooled by a distant earthquake.
    origin = Origin(time_utc=BASE, latitude=27.800, longitude=85.279, magnitude=6.5)
    outcome = process_window(
        _obs(origins=(origin,), gauge=_gauge()), reach=REACH, model_version=MODEL
    )
    assert outcome.suppression.suppressed
    assert outcome.alert_xml is not None  # hydro carries the alert on its own
    assert outcome.decision.tier.value in {"ADVISORY", "WARNING"}


def test_quiet_window_raises_no_alert() -> None:
    outcome = process_window(
        _obs(segment_lf_hf=EQ_LF_HF, segment_centroid_hz=EQ_CENTROID),
        reach=REACH,
        model_version=MODEL,
    )
    assert outcome.decision.tier.value == "NONE"
    assert outcome.alert_xml is None
    assert outcome.audit.payload["alert_raised"] is False


def test_alert_body_is_hashed_into_the_audit_record() -> None:
    outcome = process_window(_obs(gauge=_gauge()), reach=REACH, model_version=MODEL)
    assert outcome.audit.payload["alert_sha256"] is not None
    assert outcome.audit.payload["alert_raised"] is True


def test_audit_chain_written_by_run_over_verifies(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    observations = [
        _obs(segment_lf_hf=EQ_LF_HF, segment_centroid_hz=EQ_CENTROID),
        _obs(gauge=_gauge()),
        _obs(gauge=_gauge()),
    ]
    outcomes = run_over(observations, reach=REACH, model_version=MODEL, audit_log=log)
    assert len(outcomes) == 3
    assert verify_chain(tmp_path / "audit.jsonl")
    # Records are genuinely chained: each prev_hash is the previous record_hash.
    assert outcomes[1].audit.prev_hash == outcomes[0].audit.record_hash
    assert outcomes[2].audit.prev_hash == outcomes[1].audit.record_hash


def test_tampering_with_a_past_record_breaks_the_chain(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    run_over(
        [_obs(gauge=_gauge()), _obs(gauge=_gauge())],
        reach=REACH,
        model_version=MODEL,
        audit_log=log,
    )
    assert verify_chain(tmp_path / "audit.jsonl")

    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["payload"]["decision"]["tier"] = "NONE"  # rewrite history
    lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"))
    (tmp_path / "audit.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert not verify_chain(tmp_path / "audit.jsonl")


def test_audit_log_rejects_an_out_of_order_append(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    good = process_window(_obs(gauge=_gauge()), reach=REACH, model_version=MODEL, prev_hash="")
    log.append(good.audit)
    # A record built on the empty head cannot follow one already appended.
    stale = process_window(_obs(gauge=_gauge()), reach=REACH, model_version=MODEL, prev_hash="")
    with pytest.raises(ValueError, match="chain break"):
        log.append(stale.audit)


def test_audit_log_recovers_the_head_on_reopen(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    run_over([_obs(gauge=_gauge())], reach=REACH, model_version=MODEL, audit_log=AuditLog(path))
    reopened = AuditLog(path)
    # A fresh handle continues the existing chain rather than starting a new one.
    outcomes = run_over(
        [_obs(gauge=_gauge())], reach=REACH, model_version=MODEL, audit_log=reopened
    )
    assert verify_chain(path)
    assert outcomes[0].audit.prev_hash != ""


def test_health_monitor_counts_and_flags_blindness() -> None:
    health = HealthMonitor()
    # A dead station with no gauge and no detection: no live channel => blind.
    dead_seismic = _obs(
        segment_lf_hf=EQ_LF_HF, segment_centroid_hz=EQ_CENTROID, seismic_sensor_alive=False
    )
    run_over([dead_seismic], reach=REACH, model_version=MODEL, health=health)
    assert health.windows_seen == 1
    assert health.blind

    health2 = HealthMonitor()
    run_over([_obs(gauge=_gauge())], reach=REACH, model_version=MODEL, health=health2)
    assert not health2.blind
    assert health2.alerts_raised == 1


def test_run_forever_is_honestly_unimplemented() -> None:
    with pytest.raises(NotImplementedError, match="seven-day SeedLink latency run"):
        run_forever()
