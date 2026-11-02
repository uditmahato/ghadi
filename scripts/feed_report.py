"""Summarise the shadow service's window log: the latency run and the time watched (#8).

    python scripts/feed_report.py --settings deploy/ghadi.toml
    python scripts/feed_report.py --settings deploy/ghadi.toml --since 2026-11-02T00:00Z

Reads ``windows.jsonl`` in the state directory, which the service appends to once a
window, across restarts. Prints one JSON document. The delay figures are the ones
docs/LATENCY.md reports; the hours watched are what a false alarm rate is divided by.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ghadi.feedlog import summarise_feed_log  # noqa: E402
from ghadi.settings import load_settings  # noqa: E402


def parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--settings", type=Path, default=None, help="site settings TOML")
    parser.add_argument("--state-dir", type=Path, default=None, help="overrides the settings")
    parser.add_argument("--since", type=parse_utc, default=None, help="only windows from, UTC")
    args = parser.parse_args(argv)

    settings = load_settings(args.settings)
    state_dir = args.state_dir.resolve() if args.state_dir else settings.state_dir
    path = state_dir / settings.windows_path.name
    if not path.exists():
        print(f"no window log at {path}; it appears once a service with the window log runs")
        return 1
    summary = summarise_feed_log(path, settings.station_key, since=args.since, hop_s=settings.hop_s)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
