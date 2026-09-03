"""Map a station's actual archive coverage, month by month.

**Why.** Harvesting the earthquake corpus returned no waveform for 86 of 150 candidates,
84 of them in 2025. A direct check confirmed the cause is not rate limiting: the server
answers HTTP 204 "no data available" for windows in late 2025 while returning clean data
for 2026. The station metadata advertises continuous operation from 2016-05-22
open-ended, so **what the station claims to cover and what the archive actually holds
are different things**, and only the second one can be harvested.

This probes one short window per month and reports which months have data. It is a
coverage map, not a completeness measure: a month marked present may still be full of
gaps, since one probe per month cannot see them.

Any corpus must be drawn from months that are actually present, and any claim about
"six months of continuous noise" has to be checked against this first.

    python scripts/probe_availability.py
    python scripts/probe_availability.py --start 2024-01 --probe-minutes 10
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import PRIMARY_STATION  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "data" / "corpus" / "availability.json"
STATION_START = datetime(2016, 5, 22, tzinfo=UTC)


def months(start: datetime, end: datetime) -> list[datetime]:
    out = []
    cursor = datetime(start.year, start.month, 1, tzinfo=UTC)
    while cursor < end:
        out.append(cursor)
        cursor = (cursor.replace(day=28) + timedelta(days=8)).replace(day=1)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2016-05", help="YYYY-MM")
    parser.add_argument("--end", default="2026-09", help="YYYY-MM")
    parser.add_argument("--probe-minutes", type=float, default=10.0)
    parser.add_argument("--day", type=int, default=15, help="day of month to probe")
    parser.add_argument("--hour", type=int, default=6, help="UTC hour to probe")
    parser.add_argument("--network", default=PRIMARY_STATION.network)
    parser.add_argument("--station", default=PRIMARY_STATION.station)
    parser.add_argument("--location", default=PRIMARY_STATION.location)
    parser.add_argument("--channel", default=PRIMARY_STATION.channel)
    parser.add_argument("--out", default=None, help="defaults to availability_<NET>_<STA>.json")
    args = parser.parse_args(argv)

    start = datetime.strptime(args.start, "%Y-%m").replace(tzinfo=UTC)
    end = datetime.strptime(args.end, "%Y-%m").replace(tzinfo=UTC)

    client = CachedWaveformClient()
    rows: list[dict[str, Any]] = []

    for month in months(start, end):
        probe = month.replace(day=args.day, hour=args.hour)
        request = WaveformRequest(
            args.network,
            args.station,
            args.location,
            args.channel,
            probe,
            probe + timedelta(minutes=args.probe_minutes),
        )
        result = client.get_waveforms(request)
        n_samples = 0
        if result.ok:
            try:
                n_samples = int(sum(len(tr) for tr in result.stream))
            except Exception:
                n_samples = 0
        rows.append(
            {
                "month": month.strftime("%Y-%m"),
                "probe_utc": probe.isoformat(),
                "present": bool(result.ok and n_samples > 0),
                "n_samples": n_samples,
                "error": result.error,
            }
        )
        mark = "#" if rows[-1]["present"] else "."
        print(f"  {rows[-1]['month']} {mark}", flush=True)

    present = [r for r in rows if r["present"]]
    out = (
        Path(args.out)
        if args.out
        else (
            DEFAULT_OUT
            if (args.network, args.station) == (PRIMARY_STATION.network, PRIMARY_STATION.station)
            else DEFAULT_OUT.parent / f"availability_{args.network}_{args.station}.json"
        )
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "probed_utc": datetime.now(UTC).isoformat(),
                "station": f"{args.network}.{args.station}.{args.location}.{args.channel}",
                "method": (
                    f"one {args.probe_minutes:g}-minute window per month, day "
                    f"{args.day} at {args.hour:02d}:00 UTC. A month marked present may "
                    "still contain gaps; one probe cannot see them."
                ),
                "months_probed": len(rows),
                "months_present": len(present),
                "months": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n{len(present)}/{len(rows)} months have data at the probe point")
    print(f"Wrote {out}\n")

    by_year: dict[str, list[str]] = {}
    for row in rows:
        year = row["month"].split("-")[0]
        by_year.setdefault(year, []).append("#" if row["present"] else ".")
    print("  year  JFMAMJJASOND  (# present at probe, . absent)")
    for year in sorted(by_year):
        print(f"  {year}  {''.join(by_year[year])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
