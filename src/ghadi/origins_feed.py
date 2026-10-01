"""A rolling global earthquake catalogue for the live loop.

The distant earthquake check (``ghadi.teleseism``) was built and measured against a
cached catalogue, and the live loop was then started without one. In its first 20 hours
it staged one Advisory, and that Advisory was an M5.2 earthquake near Yemen whose first
waves reached Kakani at the moment of the trigger. This module is the missing feed.

Two facts shape it:

* **The catalogue is late.** A global agency publishes an origin minutes after the
  earthquake, often after its waves have already reached the station and the detector
  has decided. So the feed serves two uses: suppression when the origin is already
  known, and *explanation after the fact* when it arrives later. ``explains`` is the
  second, and the service records it against a decision already made.
* **The feed can fail.** A fetch that fails keeps the origins already held and records
  the failure. The loop never blocks on it and never treats a failed fetch as an empty
  sky.

The offline discipline holds: with ``GHADI_OFFLINE`` set the default fetcher refuses,
and a replay supplies its own origins.
"""

from __future__ import annotations

import csv
import io
import os
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .teleseism import Origin

__all__ = ["Fetcher", "RollingOrigins", "fetch_usgs", "parse_usgs_csv"]

USGS_ENDPOINT = "https://earthquake.usgs.gov/fdsnws/event/1/query"
Fetcher = Callable[[datetime, datetime, float], list[Origin]]


def parse_usgs_csv(text: str) -> list[Origin]:
    """Origins from the USGS CSV format. Rows that cannot be read are skipped."""
    out: list[Origin] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            when = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
            out.append(
                Origin(
                    time_utc=when if when.tzinfo else when.replace(tzinfo=UTC),
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    magnitude=float(row["mag"]),
                    event_id=row.get("id", ""),
                    place=row.get("place", ""),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def fetch_usgs(start: datetime, end: datetime, min_magnitude: float) -> list[Origin]:
    """Fetch origins from the public USGS service."""
    if os.environ.get("GHADI_OFFLINE"):
        raise RuntimeError("GHADI_OFFLINE is set and the catalogue feed needs the network")
    params = {
        "format": "csv",
        "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end.strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": f"{min_magnitude:g}",
        "orderby": "time-asc",
    }
    url = f"{USGS_ENDPOINT}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return parse_usgs_csv(response.read().decode("utf-8"))


@dataclass
class RollingOrigins:
    """The last few hours of global origins, refreshed on a timer.

    Args:
        fetch: where origins come from. Injectable so tests and replays never touch
            the network.
        min_magnitude: the smallest origin to hold. Kept below the suppressor's own
            threshold so the threshold can be decided there, not here.
        lookback_s: how far back to hold origins. Surface waves from the far side of
            the earth take about an hour, so two hours covers every phase window.
        refresh_s: the least time between fetches.
    """

    fetch: Fetcher = fetch_usgs
    min_magnitude: float = 4.5
    lookback_s: float = 2 * 3600.0
    refresh_s: float = 120.0
    origins: tuple[Origin, ...] = ()
    last_fetch_utc: datetime | None = None
    last_error: str | None = None
    failures: int = 0
    fetches: int = 0
    _seen: set[str] = field(default_factory=set, repr=False)

    def refresh(self, now_utc: datetime, force: bool = False) -> list[Origin]:
        """Fetch if due. Returns the origins that are new since the last fetch."""
        if (
            not force
            and self.last_fetch_utc is not None
            and (now_utc - self.last_fetch_utc).total_seconds() < self.refresh_s
        ):
            return []
        self.last_fetch_utc = now_utc
        start = now_utc - timedelta(seconds=self.lookback_s)
        try:
            fetched = self.fetch(start, now_utc + timedelta(minutes=5), self.min_magnitude)
        except Exception as exc:  # the loop must outlive the feed
            self.failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            return []
        self.fetches += 1
        self.last_error = None
        keep = {self._key(o): o for o in self.origins if o.time_utc >= start}
        new: list[Origin] = []
        for origin in fetched:
            key = self._key(origin)
            if key not in self._seen:
                self._seen.add(key)
                new.append(origin)
            keep[key] = origin  # a revised origin replaces the earlier one
        self.origins = tuple(sorted(keep.values(), key=lambda o: o.time_utc))
        return new

    @staticmethod
    def _key(origin: Origin) -> str:
        return (
            origin.event_id or f"{origin.time_utc.isoformat()}|{origin.latitude}|{origin.longitude}"
        )

    def current(self, now_utc: datetime) -> tuple[Origin, ...]:
        """The origins held, refreshing first if a fetch is due."""
        self.refresh(now_utc)
        return self.origins

    def status(self) -> dict[str, object]:
        return {
            "origins_held": len(self.origins),
            "fetches": self.fetches,
            "failures": self.failures,
            "last_fetch_utc": self.last_fetch_utc.isoformat() if self.last_fetch_utc else None,
            "last_error": self.last_error,
        }
