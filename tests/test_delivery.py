"""Issue #36: no path exists from a decision to an outbound message without a person."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import ghadi.delivery as delivery
from ghadi.delivery import (
    Approval,
    DeliveryError,
    FileSink,
    Outbox,
    StagedAlert,
    verify_delivery_chain,
)
from ghadi.hydro import synthetic_surge
from ghadi.service import GaugeObservation, WindowObservation, process_window

DETECTED = datetime(2026, 8, 26, 2, 52, 24, tzinfo=UTC)


def warning_outcome():  # type: ignore[no-untyped-def]
    times, stage = synthetic_surge()
    obs = WindowObservation(
        window_start_utc=DETECTED - timedelta(seconds=120),
        detected_utc=DETECTED,
        segment_lf_hf=4.9188,
        segment_centroid_hz=1.8852,
        gauge=GaugeObservation(times.tolist(), stage.tolist(), sensor_alive=True, name="gauge"),
        event_id="TEST-EVENT",
    )
    return process_window(obs, reach="TRISHULI-R07", model_version="test")


def quiet_outcome():  # type: ignore[no-untyped-def]
    obs = WindowObservation(
        window_start_utc=DETECTED - timedelta(seconds=120),
        detected_utc=DETECTED,
        segment_lf_hf=1.66,
        segment_centroid_hz=3.04,
        event_id="TEST-QUIET",
    )
    return process_window(obs, reach="TRISHULI-R07", model_version="test")


class FlakySink:
    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.sent: list[str] = []

    @property
    def name(self) -> str:
        return "flaky"

    def send(self, staged: StagedAlert, approval: Approval) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("down")
        self.sent.append(staged.staged_id)
        return "ok"


def outbox(tmp_path: Path, *sinks) -> Outbox:  # type: ignore[no-untyped-def]
    return Outbox(
        tmp_path / "delivery.jsonl",
        sinks or (FileSink(tmp_path / "desk"),),
        staging_dir=tmp_path / "staged",
        attempts=3,
        sleep=lambda s: None,
    )


def test_a_quiet_outcome_stages_nothing(tmp_path: Path) -> None:
    assert outbox(tmp_path).stage(quiet_outcome()) is None


def test_stage_approve_deliver_is_the_only_road(tmp_path: Path) -> None:
    box = outbox(tmp_path)
    staged = box.stage(warning_outcome())
    assert staged is not None and staged.tier == "WARNING"
    assert [s.staged_id for s in box.pending()] == [staged.staged_id]

    approval = box.approve(staged.staged_id, "Duty Officer A", note="checked the gauge")
    receipts = box.deliver(staged.staged_id, approval)

    assert len(receipts) == 1
    assert (tmp_path / "desk" / f"{staged.staged_id}.xml").exists()
    assert box.pending() == []
    kinds = [e["kind"] for e in box.log.entries()]
    assert kinds == ["staged", "approved", "delivered"]
    assert verify_delivery_chain(tmp_path / "delivery.jsonl")


def test_delivery_without_an_approval_is_impossible_by_signature(tmp_path: Path) -> None:
    box = outbox(tmp_path)
    staged = box.stage(warning_outcome())
    assert staged is not None
    with pytest.raises(TypeError):
        box.deliver(staged.staged_id)  # type: ignore[call-arg]


def test_an_approval_for_another_message_is_refused(tmp_path: Path) -> None:
    box = outbox(tmp_path)
    first = box.stage(warning_outcome())
    assert first is not None
    approval = box.approve(first.staged_id, "Duty Officer A")
    forged = Approval(
        "someone-else", approval.alert_sha256, "Duty Officer A", approval.approved_utc
    )
    with pytest.raises(DeliveryError, match="different message"):
        box.deliver(first.staged_id, forged)


def test_an_approval_not_on_record_is_refused(tmp_path: Path) -> None:
    box = outbox(tmp_path)
    staged = box.stage(warning_outcome())
    assert staged is not None
    made_up = Approval(staged.staged_id, staged.alert_sha256, "Nobody", datetime.now(tz=UTC))
    with pytest.raises(DeliveryError, match="not on record"):
        box.deliver(staged.staged_id, made_up)


def test_the_approver_must_be_a_person(tmp_path: Path) -> None:
    box = outbox(tmp_path)
    staged = box.stage(warning_outcome())
    assert staged is not None
    for name in ("", "  ", "system", "auto"):
        with pytest.raises(DeliveryError, match="name a person"):
            box.approve(staged.staged_id, name)


def test_a_message_altered_on_disk_cannot_be_delivered(tmp_path: Path) -> None:
    box = outbox(tmp_path)
    staged = box.stage(warning_outcome())
    assert staged is not None
    approval = box.approve(staged.staged_id, "Duty Officer A")
    path = tmp_path / "staged" / f"{staged.staged_id}.json"
    path.write_text(path.read_text(encoding="utf-8").replace("<info>", "<info><!-- x -->", 1))
    with pytest.raises(DeliveryError, match="altered"):
        box.deliver(staged.staged_id, approval)


def test_failures_are_retried_then_recorded(tmp_path: Path) -> None:
    flaky = FlakySink(fail_times=2)
    box = outbox(tmp_path, flaky)
    staged = box.stage(warning_outcome())
    assert staged is not None
    approval = box.approve(staged.staged_id, "Duty Officer A")
    receipts = box.deliver(staged.staged_id, approval)
    assert receipts[0].attempts == 3 and flaky.sent == [staged.staged_id]

    dead = FlakySink(fail_times=99)
    box2 = outbox(tmp_path / "two", dead)
    staged2 = box2.stage(warning_outcome())
    assert staged2 is not None
    approval2 = box2.approve(staged2.staged_id, "Duty Officer B")
    with pytest.raises(DeliveryError, match="down"):
        box2.deliver(staged2.staged_id, approval2)
    assert [e["kind"] for e in box2.log.entries()][-1] == "failed"
    assert box2.pending(), "a failed message is still pending, not lost"


def test_rejection_closes_a_message_without_sending(tmp_path: Path) -> None:
    box = outbox(tmp_path)
    staged = box.stage(warning_outcome())
    assert staged is not None
    box.reject(staged.staged_id, "Duty Officer A", note="gauge reading was a test")
    assert box.pending() == []
    assert not (tmp_path / "desk").exists()


def test_no_public_sink_exists_in_the_module() -> None:
    """Tier T1 only: officials by file or webhook. Nothing that broadcasts."""
    names = {name.lower() for name, _ in inspect.getmembers(delivery, inspect.isclass)}
    for banned in ("sms", "broadcast", "public", "cellbroadcast", "twilio"):
        assert not any(banned in n for n in names), names
