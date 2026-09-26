"""Deliver an advisory to duty officers, behind a human gate (issue #36).

The pipeline ends in a valid CAP message and, until now, stopped there. This module is
the step after it, built for tier T1 in the handoff: an advisory reaches named officials
only, and a person forwards it. It is deliberately narrow.

* **Nothing leaves without an approval.** An alert is *staged*, a named person
  *approves* it, and only then can it be *delivered*. There is no function that sends
  an alert without an ``Approval`` value, and an approval names who gave it, when, and
  the exact message hash it covers. The tests prove the gate cannot be walked around.
* **Every step is on a hash chain.** Staging, approval, delivery, failure, and
  rejection are records in an append only log chained like the audit log, so the
  history of who did what to which message is tamper evident.
* **Sinks are for officials, not the public.** A file sink and a webhook sink exist.
  Neither is an SMS gateway or a broadcast, and none will be added here without the
  authorisation tier T3 requires.
* **Retries are bounded and recorded.** A sink that fails is retried with a growing
  wait, and a message that could not be delivered is logged as such, never dropped.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .service import ServiceOutcome

__all__ = [
    "Approval",
    "DeliveryError",
    "DeliveryLog",
    "FileSink",
    "Outbox",
    "Receipt",
    "Sink",
    "StagedAlert",
    "WebhookSink",
    "verify_delivery_chain",
]


class DeliveryError(RuntimeError):
    """A delivery that must not happen, or one that could not."""


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class StagedAlert:
    """An alert waiting for a person. Immutable: approval covers exactly this content."""

    staged_id: str
    event_id: str
    tier: str
    alert_sha256: str
    alert_xml: str
    staged_utc: datetime
    audit_record_hash: str  # the decision this alert came from
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "staged_id": self.staged_id,
            "event_id": self.event_id,
            "tier": self.tier,
            "alert_sha256": self.alert_sha256,
            "staged_utc": self.staged_utc.isoformat(),
            "audit_record_hash": self.audit_record_hash,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class Approval:
    """A named person's decision to send one specific message."""

    staged_id: str
    alert_sha256: str
    approver: str
    approved_utc: datetime
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "staged_id": self.staged_id,
            "alert_sha256": self.alert_sha256,
            "approver": self.approver,
            "approved_utc": self.approved_utc.isoformat(),
            "note": self.note,
        }


@dataclass(frozen=True)
class Receipt:
    sink: str
    staged_id: str
    delivered_utc: datetime
    detail: str
    attempts: int


class Sink(Protocol):
    """Somewhere an approved advisory can go. Officials only."""

    @property
    def name(self) -> str: ...

    def send(self, staged: StagedAlert, approval: Approval) -> str:
        """Deliver, returning a short receipt. Raise on failure."""
        ...


@dataclass
class FileSink:
    """Write the approved message to a directory a duty desk watches."""

    directory: Path

    @property
    def name(self) -> str:
        return f"file:{self.directory}"

    def send(self, staged: StagedAlert, approval: Approval) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{staged.staged_id}.xml"
        target.write_text(staged.alert_xml, encoding="utf-8")
        meta = self.directory / f"{staged.staged_id}.approval.json"
        meta.write_text(json.dumps(approval.as_dict(), indent=2), encoding="utf-8")
        return str(target)


@dataclass
class WebhookSink:
    """POST the approved message and its approval to a pre agreed endpoint."""

    url: str
    timeout_s: float = 10.0

    @property
    def name(self) -> str:
        return f"webhook:{self.url}"

    def send(self, staged: StagedAlert, approval: Approval) -> str:
        body = json.dumps(
            {"alert": staged.as_dict(), "approval": approval.as_dict(), "cap_xml": staged.alert_xml}
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return f"HTTP {response.status}"
        except urllib.error.URLError as exc:
            raise DeliveryError(f"webhook failed: {exc}") from exc


class DeliveryLog:
    """Append only, hash chained record of every staging, approval, and delivery."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.head = self._recover_head()

    def _recover_head(self) -> str:
        if not self.path.exists():
            return ""
        head = ""
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                head = json.loads(line)["record_hash"]
        return head

    def append(self, kind: str, payload: dict[str, Any]) -> str:
        entry = {"kind": kind, "utc": _now().isoformat(), **payload}
        record_hash = _sha(self.head + _canonical(entry))
        line = _canonical({"payload": entry, "prev_hash": self.head, "record_hash": record_hash})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self.head = record_hash
        return record_hash

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)["payload"]
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


def verify_delivery_chain(path: str | Path) -> bool:
    p = Path(path)
    if not p.exists():
        return True
    prev = ""
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["prev_hash"] != prev:
            return False
        if _sha(prev + _canonical(entry["payload"])) != entry["record_hash"]:
            return False
        prev = entry["record_hash"]
    return True


class Outbox:
    """Stage, approve, deliver. In that order, and never without the middle step.

    Args:
        log_path: the delivery log.
        sinks: where approved advisories go.
        staging_dir: where staged messages wait on disk, so an approval can come from a
            different process, hours later, from a person at a desk.
        attempts: delivery attempts per sink before it is recorded as failed.
        sleep: the wait between attempts, injectable for tests.
    """

    def __init__(
        self,
        log_path: str | Path,
        sinks: Iterable[Sink],
        *,
        staging_dir: str | Path,
        attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.log = DeliveryLog(log_path)
        self.sinks = tuple(sinks)
        self.staging_dir = Path(staging_dir)
        self.attempts = max(1, attempts)
        self._sleep = sleep

    # -- staging -------------------------------------------------------------------------
    def stage(self, outcome: ServiceOutcome) -> StagedAlert | None:
        """Put an outcome's alert in the queue for a person. Returns None if no alert."""
        if outcome.alert_xml is None:
            return None
        sha = _sha(outcome.alert_xml)
        staged = StagedAlert(
            staged_id=f"{outcome.audit.payload['event_id']}-{outcome.audit.record_hash[:12]}",
            event_id=str(outcome.audit.payload["event_id"]),
            tier=outcome.decision.tier.value,
            alert_sha256=sha,
            alert_xml=outcome.alert_xml,
            staged_utc=_now(),
            audit_record_hash=outcome.audit.record_hash,
            rationale=outcome.decision.rationale,
        )
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        (self.staging_dir / f"{staged.staged_id}.json").write_text(
            json.dumps({**staged.as_dict(), "alert_xml": staged.alert_xml}, indent=2),
            encoding="utf-8",
        )
        self.log.append("staged", staged.as_dict())
        return staged

    def pending(self) -> list[StagedAlert]:
        """Every staged alert not yet delivered or rejected."""
        done = {
            e["staged_id"] for e in self.log.entries() if e["kind"] in ("delivered", "rejected")
        }
        out: list[StagedAlert] = []
        for path in sorted(self.staging_dir.glob("*.json")):
            staged = self._load(path)
            if staged.staged_id not in done:
                out.append(staged)
        return out

    def get(self, staged_id: str) -> StagedAlert:
        path = self.staging_dir / f"{staged_id}.json"
        if not path.exists():
            raise DeliveryError(f"no staged alert {staged_id!r}")
        return self._load(path)

    @staticmethod
    def _load(path: Path) -> StagedAlert:
        raw = json.loads(path.read_text(encoding="utf-8"))
        staged = StagedAlert(
            staged_id=raw["staged_id"],
            event_id=raw["event_id"],
            tier=raw["tier"],
            alert_sha256=raw["alert_sha256"],
            alert_xml=raw["alert_xml"],
            staged_utc=datetime.fromisoformat(raw["staged_utc"]),
            audit_record_hash=raw["audit_record_hash"],
            rationale=raw["rationale"],
        )
        if _sha(staged.alert_xml) != staged.alert_sha256:
            raise DeliveryError(f"staged alert {staged.staged_id} was altered on disk")
        return staged

    # -- the gate --------------------------------------------------------------------------
    def approve(self, staged_id: str, approver: str, note: str = "") -> Approval:
        """A named person approves one specific message."""
        if not approver.strip() or approver.strip().lower() in ("system", "auto", "ghadi"):
            raise DeliveryError("an approval must name a person")
        staged = self.get(staged_id)
        approval = Approval(
            staged_id=staged.staged_id,
            alert_sha256=staged.alert_sha256,
            approver=approver.strip(),
            approved_utc=_now(),
            note=note,
        )
        self.log.append("approved", approval.as_dict())
        return approval

    def reject(self, staged_id: str, approver: str, note: str = "") -> None:
        if not approver.strip():
            raise DeliveryError("a rejection must name a person")
        staged = self.get(staged_id)
        self.log.append(
            "rejected",
            {"staged_id": staged.staged_id, "approver": approver.strip(), "note": note},
        )

    def deliver(self, staged_id: str, approval: Approval) -> list[Receipt]:
        """Send an approved message to every sink. The approval is checked, not trusted."""
        staged = self.get(staged_id)
        if approval.staged_id != staged.staged_id:
            raise DeliveryError("approval is for a different message")
        if approval.alert_sha256 != staged.alert_sha256:
            raise DeliveryError("approval covers different content than the staged message")
        if not any(
            e["kind"] == "approved"
            and e["staged_id"] == staged.staged_id
            and e["approver"] == approval.approver
            for e in self.log.entries()
        ):
            raise DeliveryError("approval is not on record")

        receipts: list[Receipt] = []
        failures: list[str] = []
        for sink in self.sinks:
            wait = 1.0
            for attempt in range(1, self.attempts + 1):
                try:
                    detail = sink.send(staged, approval)
                except Exception as exc:  # any failure counts; the log says which
                    if attempt == self.attempts:
                        failures.append(f"{sink.name}: {exc}")
                        self.log.append(
                            "failed",
                            {
                                "staged_id": staged.staged_id,
                                "sink": sink.name,
                                "attempts": attempt,
                                "error": str(exc),
                            },
                        )
                    else:
                        self._sleep(wait)
                        wait = min(wait * 2, 30.0)
                    continue
                receipts.append(Receipt(sink.name, staged.staged_id, _now(), detail, attempt))
                self.log.append(
                    "delivered",
                    {
                        "staged_id": staged.staged_id,
                        "sink": sink.name,
                        "approver": approval.approver,
                        "attempts": attempt,
                        "detail": detail,
                    },
                )
                break
        if failures and not receipts:
            raise DeliveryError("; ".join(failures))
        return receipts
