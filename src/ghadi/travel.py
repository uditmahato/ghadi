"""Surge travel-time tables per river reach — M4, not started.

The deliverable is a table mapping (river reach, source location) to arrival times at
named settlements, calibrated against the 26 August 2026 event's observed progression
(~9 m in 30 minutes on the Trishuli; 20-40 minutes from initiation to the first
settlements). Reaches to cover first (issue 4.1): Lhende-Bhote Koshi-Trishuli,
Sun Koshi, Tamakoshi.

This is what converts a detection into a lead-time claim, and the lead-time claim is
the headline result of the whole project (M5). It is not on the latency-critical path:
tables are precomputed offline and looked up in microseconds.
"""

from __future__ import annotations


def arrival_estimates_min(
    river_reach: str, source_lat: float, source_lon: float
) -> dict[str, float]:
    """Estimated surge arrival time in minutes at each settlement on a reach.

    Raises:
        NotImplementedError: always, until M4.
    """
    raise NotImplementedError(
        "Travel-time tables are M4 (issue 4.1). They must be calibrated against the "
        "observed 2026 progression before any lead-time figure is quoted."
    )
