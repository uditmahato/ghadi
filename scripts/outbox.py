"""The duty officer's side of the human gate (issue #36).

The shadow service stages every alert it would have raised. Nothing goes further until
a named person looks at it here and says so.

    python scripts/outbox.py list
    python scripts/outbox.py show GHADI-LIVE-3f2a9c1b0d4e
    python scripts/outbox.py approve GHADI-LIVE-3f2a9c1b0d4e --by "A. Officer" --note "gauge agrees"
    python scripts/outbox.py reject GHADI-LIVE-3f2a9c1b0d4e --by "A. Officer" --note "test signal"
    python scripts/outbox.py verify

``approve`` delivers to the configured sinks in the same step, because an approval that
is not acted on is a message nobody sent. Sinks are a file directory for the desk and,
if set, a webhook agreed with the receiving office. There is no public sink.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ghadi.delivery import (  # noqa: E402
    DeliveryError,
    FileSink,
    Outbox,
    Sink,
    WebhookSink,
    verify_delivery_chain,
)
from ghadi.settings import load_settings  # noqa: E402


def build_outbox(
    settings_path: Path | None, webhook: str | None, state_dir: Path | None = None
) -> Outbox:
    s = load_settings(settings_path)
    if state_dir is not None:
        from dataclasses import replace

        s = replace(s, state_dir=state_dir.resolve())
    sinks: list[Sink] = [FileSink(s.outbox_dir)]
    if webhook:
        sinks.append(WebhookSink(webhook))
    return Outbox(s.delivery_log_path, sinks, staging_dir=s.staging_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--settings", type=Path, default=None, help="site settings TOML")
    parser.add_argument("--state-dir", type=Path, default=None, help="overrides the settings")
    parser.add_argument("--webhook", default=None, help="an agreed endpoint for officials")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="staged alerts waiting for a decision")
    show = sub.add_parser("show", help="print one staged alert in full")
    show.add_argument("staged_id")
    for name in ("approve", "reject"):
        p = sub.add_parser(name)
        p.add_argument("staged_id")
        p.add_argument("--by", required=True, help="your name; it goes on the record")
        p.add_argument("--note", default="")
    sub.add_parser("verify", help="check the delivery log's hash chain")
    args = parser.parse_args(argv)

    box = build_outbox(args.settings, args.webhook, args.state_dir)
    try:
        if args.command == "list":
            pending = box.pending()
            if not pending:
                print("nothing waiting")
            for s in pending:
                print(f"{s.staged_id}  {s.tier:<8} staged {s.staged_utc.isoformat()}")
                print(f"    {s.rationale[:110]}")
        elif args.command == "show":
            s = box.get(args.staged_id)
            print(f"{s.staged_id} {s.tier} event {s.event_id} staged {s.staged_utc.isoformat()}")
            print(f"decision record {s.audit_record_hash}")
            print(f"rationale: {s.rationale}\n")
            print(s.alert_xml)
        elif args.command == "approve":
            approval = box.approve(args.staged_id, args.by, args.note)
            receipts = box.deliver(args.staged_id, approval)
            for r in receipts:
                print(f"delivered to {r.sink} after {r.attempts} attempt(s): {r.detail}")
        elif args.command == "reject":
            box.reject(args.staged_id, args.by, args.note)
            print(f"rejected {args.staged_id}; nothing was sent")
        elif args.command == "verify":
            ok = verify_delivery_chain(box.log.path)
            print("delivery log chain intact" if ok else "DELIVERY LOG CHAIN BROKEN")
            return 0 if ok else 2
    except DeliveryError as exc:
        print(f"refused: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
