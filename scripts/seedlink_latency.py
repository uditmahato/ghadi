"""Issue 0.1 — measure real-time NK.KKN latency over SeedLink.

**This determines whether the project is viable in real time at all.** Everything
verified so far is *archive* retrieval; the achievable real-time latency is unmeasured
and is the single most important unknown in the project (Blocker B4). If latency
exceeds ~120 s, GHADI becomes retrospective-analysis-only and must be re-scoped
honestly.

Usage:

    # Collect for 7 days (the handoff asks for a 7-day distribution)
    python scripts/seedlink_latency.py --hours 168 --out latency_log.csv

    # Summarise a collected log
    python scripts/seedlink_latency.py --report latency_log.csv

The measurement is: for each received packet, ``now - packet_end_time``. That is the
age of the newest sample in the packet at the moment it reached us, which is the
quantity the detection path actually pays.

Writes one CSV row per packet so the run is resumable and inspectable mid-flight; a
7-day run should not hold its results in memory.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_SERVER = "rtserve.iris.washington.edu:18000"
DEFAULT_NSLC = ("NK", "KKN", "", "BHZ")


def collect(
    server: str,
    hours: float,
    out_path: Path,
    network: str,
    station: str,
    location: str,
    channel: str,
) -> int:
    """Stream packets and log per-packet arrival delay. Returns packets logged."""
    from obspy.clients.seedlink.easyseedlink import create_client

    deadline = time.monotonic() + hours * 3600.0
    count = 0
    new_file = not out_path.exists()
    handle = out_path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(handle)
    if new_file:
        writer.writerow(
            ["received_utc", "packet_start_utc", "packet_end_utc", "latency_s", "n_samples", "nslc"]
        )
        handle.flush()

    def on_data(trace: object) -> None:
        nonlocal count
        now = datetime.now(UTC)
        end = trace.stats.endtime.datetime.replace(tzinfo=UTC)  # type: ignore[attr-defined]
        start = trace.stats.starttime.datetime.replace(tzinfo=UTC)  # type: ignore[attr-defined]
        latency = (now - end).total_seconds()
        writer.writerow(
            [
                now.isoformat(timespec="milliseconds"),
                start.isoformat(timespec="milliseconds"),
                end.isoformat(timespec="milliseconds"),
                f"{latency:.3f}",
                len(trace.data),  # type: ignore[attr-defined]
                f"{network}.{station}.{location}.{channel}",
            ]
        )
        handle.flush()  # a 7-day run must survive being killed
        count += 1
        if count % 20 == 0:
            print(f"  {count} packets, last latency {latency:.1f}s", flush=True)
        if time.monotonic() > deadline:
            raise KeyboardInterrupt("collection window elapsed")

    print(f"Connecting to {server} for {network}.{station}.{location}.{channel} ...", flush=True)
    client = create_client(server, on_data=on_data)
    client.select_stream(network, station, channel)
    try:
        client.run()
    except KeyboardInterrupt:
        print("\nCollection stopped.", flush=True)
    finally:
        handle.close()
    return count


def report(path: Path) -> None:
    """Print the latency distribution. This is the number that gates the project."""
    with path.open(encoding="utf-8") as fh:
        latencies = [float(row["latency_s"]) for row in csv.DictReader(fh)]

    if not latencies:
        print("No packets logged.")
        return

    latencies.sort()

    def percentile(p: float) -> float:
        return latencies[min(int(p / 100.0 * len(latencies)), len(latencies) - 1)]

    print(f"packets       : {len(latencies)}")
    print(f"median        : {statistics.median(latencies):.1f} s")
    print(f"mean          : {statistics.fmean(latencies):.1f} s")
    print(f"p90           : {percentile(90):.1f} s")
    print(f"p95           : {percentile(95):.1f} s")
    print(f"p99           : {percentile(99):.1f} s")
    print(f"max           : {latencies[-1]:.1f} s")
    print()
    p95 = percentile(95)
    if p95 > 120.0:
        print(
            f"VERDICT: p95 latency {p95:.0f}s exceeds the ~120 s viability threshold.\n"
            "Per Blocker B4, real-time operation is not viable on this feed and the\n"
            "project must be re-scoped to retrospective analysis, honestly and in writing."
        )
    else:
        print(
            f"VERDICT: p95 latency {p95:.0f}s is within the ~120 s threshold. Real-time\n"
            "operation is viable on this feed; the remaining latency budget goes to\n"
            "detection and dissemination (end-to-end target 180 s)."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument(
        "--hours", type=float, default=168.0, help="collection duration (default: 7 days)"
    )
    parser.add_argument("--out", type=Path, default=Path("latency_log.csv"))
    parser.add_argument("--report", type=Path, help="summarise an existing log and exit")
    parser.add_argument("--network", default=DEFAULT_NSLC[0])
    parser.add_argument("--station", default=DEFAULT_NSLC[1])
    parser.add_argument("--location", default=DEFAULT_NSLC[2])
    parser.add_argument("--channel", default=DEFAULT_NSLC[3])
    args = parser.parse_args(argv)

    if args.report:
        report(args.report)
        return 0

    count = collect(
        args.server, args.hours, args.out, args.network, args.station, args.location, args.channel
    )
    print(f"Logged {count} packets to {args.out}")
    if count:
        print()
        report(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
