"""Fetch and cache waveform windows for every catalogue event.

Populates ``data/cache`` so later runs — and Experiment 001 — work offline. Events
predating the primary station (NK.KKN operates from 2016-05-22) will fail; that is
expected and is reported, not hidden.

    python scripts/fetch_event_windows.py
    python scripts/fetch_event_windows.py --pre-s 300 --post-s 1800
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from ghadi.catalog import load_catalog
from ghadi.config import PRIMARY_STATION
from ghadi.fdsn import CachedWaveformClient, WaveformRequest

STATION_START = "2016-05-22"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pre-s", type=float, default=600.0, help="seconds before origin")
    parser.add_argument("--post-s", type=float, default=2100.0, help="seconds after origin")
    args = parser.parse_args(argv)

    client = CachedWaveformClient()
    events = load_catalog()
    print(f"{len(events)} catalogue events; station {PRIMARY_STATION.nslc}\n")

    ok = failed = 0
    for event in events:
        request = WaveformRequest(
            PRIMARY_STATION.network,
            PRIMARY_STATION.station,
            PRIMARY_STATION.location,
            PRIMARY_STATION.channel,
            event.origin_utc - timedelta(seconds=args.pre_s),
            event.origin_utc + timedelta(seconds=args.post_s),
        )
        result = client.get_waveforms(request)
        if result.ok:
            ok += 1
            source = "cache" if result.cache_hit else "network"
            print(f"  OK      {event.event_id}  ({source})")
        else:
            failed += 1
            note = ""
            if event.origin_utc.date().isoformat() < STATION_START:
                note = f"  [expected: predates {PRIMARY_STATION.nslc} start {STATION_START}]"
            print(f"  FAILED  {event.event_id}: {result.error}{note}")

    print(f"\n{ok} retrieved, {failed} failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
