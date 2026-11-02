"""A line for every window the live loop sees, kept on disk (issue #8).

The audit log records decisions, so a quiet hour leaves nothing in it. The latency run
and the false alarm rate both need the quiet hours too: every window's feed delay, and
how long the system was actually watching. Until now those lived in memory
(``ghadi.live.FeedStats``) and in the system journal, so every restart reset the
figures and the weekly backup of the state directory missed them.

This file is a measurement record, not a decision record. It is not hash chained: a
line cut short by a crash is skipped when the file is read, and nothing is decided from
it. Each start and stop of the service is written too, so the time the system was not
watching is on the record as well.

The file grows by about 350 kB a day at one window a minute.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from .live import WindowVerdict

__all__ = ["FeedLog", "read_feed_log", "summarise_feed_log"]

# Verdicts that are not the primary station's own window: a partner station's window,
# and a decision issued again once a partner corroborated it. Neither is a new minute of
# watching, so neither is counted.
_NOT_A_PRIMARY_WINDOW = frozenset({"partner", "upgraded"})


def _now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class FeedLog:
    """Append one JSON line per event to ``path``."""

    path: Path

    def _write(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, separators=(",", ":"), default=str) + "\n")

    def start(self, *, station: str, server: str, window_s: float, hop_s: float) -> None:
        self._write(
            {
                "kind": "start",
                "utc": _now().isoformat(),
                "station": station,
                "server": server,
                "window_s": window_s,
                "hop_s": hop_s,
            }
        )

    def window(self, verdict: WindowVerdict, *, received_utc: datetime | None = None) -> None:
        w = verdict.window
        delay = w.max_delay_s if math.isfinite(w.max_delay_s) else None
        self._write(
            {
                "kind": "window",
                "utc": (received_utc or _now()).isoformat(),
                "station": w.station,
                "start_utc": w.start_utc.isoformat(),
                "end_utc": w.end_utc.isoformat(),
                "reason": verdict.reason,
                "stale": verdict.stale,
                "usable": round(w.usable_fraction, 4),
                "packets": w.n_packets,
                "delay_s": None if delay is None else round(delay, 2),
            }
        )

    def stop(self, *, feed: dict[str, float | int]) -> None:
        self._write({"kind": "stop", "utc": _now().isoformat(), "feed": feed})


def read_feed_log(path: str | Path) -> list[dict[str, Any]]:
    """Every whole line in the file. A line cut short by a crash is skipped."""
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and "kind" in entry:
            out.append(entry)
    return out


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return round(float(np.percentile(np.asarray(values, dtype=float), q)), 2)


def summarise_feed_log(
    path: str | Path,
    station: str,
    *,
    since: datetime | None = None,
    hop_s: float | None = None,
    outage_s: float = 120.0,
) -> dict[str, Any]:
    """The figures the latency run and the false alarm rate need, across restarts.

    Delays are taken from windows that arrived on time, as ``FeedStats`` does: a window
    from a backlog after an outage measures the outage, not the feed. An interruption is
    a gap between two consecutive windows longer than one hop plus ``outage_s``, the
    same 120 s threshold docs/LATENCY.md uses.
    """
    entries = read_feed_log(path)
    starts = [e for e in entries if e["kind"] == "start"]
    if hop_s is None:
        hop_s = float(starts[-1]["hop_s"]) if starts else 60.0
    windows = [
        e
        for e in entries
        if e["kind"] == "window"
        and e.get("station") == station
        and e.get("reason") not in _NOT_A_PRIMARY_WINDOW
    ]
    if since is not None:
        windows = [w for w in windows if datetime.fromisoformat(w["start_utc"]) >= since]
        starts = [s for s in starts if datetime.fromisoformat(s["utc"]) >= since]
    # A window that appears twice, for example when two runs overlap, counts once.
    by_start: dict[str, dict[str, Any]] = {}
    for w in windows:
        by_start.setdefault(w["start_utc"], w)
    unique = [by_start[k] for k in sorted(by_start)]

    on_time = [w for w in unique if not w.get("stale")]
    delays = [float(w["delay_s"]) for w in on_time if w.get("delay_s") is not None]
    usable = [w for w in unique if w.get("reason") != "unusable"]
    reasons: dict[str, int] = {}
    for w in unique:
        reasons[w["reason"]] = reasons.get(w["reason"], 0) + 1

    gaps: list[float] = []
    times = [datetime.fromisoformat(w["start_utc"]) for w in unique]
    for a, b in pairwise(times):
        gap = (b - a).total_seconds()
        if gap > hop_s + outage_s:
            gaps.append(gap - hop_s)

    return {
        "station": station,
        "first_window_utc": unique[0]["start_utc"] if unique else None,
        "last_window_utc": unique[-1]["start_utc"] if unique else None,
        "service_starts": len(starts),
        "windows": len(unique),
        "usable_windows": len(usable),
        # Each window adds one hop of new time watched; the windows overlap.
        "hours_watched": round(len(usable) * hop_s / 3600.0, 2),
        "stale_windows": len(unique) - len(on_time),
        "reasons": reasons,
        "delay_p50_s": _percentile(delays, 50),
        "delay_p95_s": _percentile(delays, 95),
        "delay_p99_s": _percentile(delays, 99),
        "delay_max_s": round(max(delays), 2) if delays else None,
        "interruptions_over_120_s": len(gaps),
        "longest_interruption_s": round(max(gaps), 1) if gaps else None,
    }
