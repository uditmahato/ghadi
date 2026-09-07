"""DHM gauge-telemetry ingestion — the swappable loader behind the hydro detector.

``ghadi.hydro.detect_anomaly`` takes a clean ``(times_s, stage_m)`` pair on purpose, so
that the day DHM telemetry access is granted (Blocker B2) only this module changes. This
is that module: it turns a raw logger export into the clean pair the detector consumes,
and it establishes the one thing the detector must never guess — whether the sensor is
still alive.

Real telemetry is not clean. This adapter handles what a DHM logger export actually
carries: coarse and irregular 5-minute sampling, out-of-order and duplicate timestamps,
sentinel values for "no reading" (-9999 and friends), physically impossible readings,
and units that may be centimetres or datum-relative rather than metres. Everything it
drops it counts and names, because an adapter that silently discards data misreports the
health of the channel it feeds.

**Liveness is an ingestion-layer fact.** ``ghadi.fusion.channel_from_hydro`` documents
that whether a gauge is still reporting cannot be read off a short series — it is a
question of whether the expected next packet arrived. That question is answered here,
against an ``as_of`` time, and a stale gauge is reported dead rather than quiet. A dead
channel is not a low-risk channel (exp008, PR #12).

No network access lives here — that is the live DHM client, which needs the agreement.
This is the format-level adapter it will sit on top of.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from .config import DEFAULT, DhmConfig


@dataclass(frozen=True)
class GaugeSeries:
    """A cleaned gauge series, ready for ``ghadi.hydro.detect_anomaly``."""

    times_s: np.ndarray  # seconds relative to origin_utc, strictly increasing
    stage_m: np.ndarray  # metres, sentinels and bad readings removed
    origin_utc: datetime | None  # timestamp of the first surviving sample
    sensor_alive: bool | None  # None => not assessed (no as_of supplied)
    n_input: int
    n_dropped: int
    dropped: dict[str, int]  # reason -> count
    median_interval_s: float | None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def detector_input(self) -> tuple[np.ndarray, np.ndarray]:
        """The ``(times_s, stage_m)`` pair the hydro detector consumes."""
        return self.times_s, self.stage_m


def _to_epoch_s(ts: datetime | float | int) -> float:
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            raise ValueError(
                "naive datetime in gauge telemetry; timestamps must be timezone-aware "
                "(Nepal Standard Time is UTC+05:45 and must be explicit, never assumed)"
            )
        return ts.timestamp()
    return float(ts)


def ingest(
    timestamps: Sequence[datetime | float],
    values: Sequence[float],
    *,
    unit: str = "m",
    datum_offset_m: float = 0.0,
    as_of: datetime | None = None,
    config: DhmConfig | None = None,
) -> GaugeSeries:
    """Clean a raw gauge export into a :class:`GaugeSeries`.

    Args:
        timestamps: per-sample time, either timezone-aware datetimes or epoch seconds.
        values: per-sample stage in ``unit``.
        unit: ``"m"`` or ``"cm"``. DHM loggers vary; the export must say which.
        datum_offset_m: added to every stage after unit conversion, for gauges that
            report relative to a local datum rather than an absolute level.
        as_of: the ingestion time, used to judge liveness. If omitted, liveness is left
            unassessed (``sensor_alive=None``) rather than assumed alive — a dead sensor
            defaulted to alive would enter fusion as a quiet, low-risk channel, which is
            the exact failure PR #12 exists to prevent.
    """
    cfg = config or DEFAULT.dhm
    if len(timestamps) != len(values):
        raise ValueError("timestamps and values must be the same length")
    if unit not in ("m", "cm"):
        raise ValueError(f"unsupported unit {unit!r}; expected 'm' or 'cm'")
    scale = 0.01 if unit == "cm" else 1.0

    n_input = len(values)
    dropped: dict[str, int] = {}

    def _drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    cleaned: list[tuple[float, float]] = []
    sentinels = set(cfg.sentinel_values)
    for ts, raw in zip(timestamps, values, strict=True):
        epoch = _to_epoch_s(ts)
        v = float(raw)
        if v in sentinels:
            _drop("sentinel")
            continue
        if not np.isfinite(v):
            _drop("nan_or_inf")
            continue
        stage = v * scale + datum_offset_m
        if not (cfg.min_plausible_stage_m <= stage <= cfg.max_plausible_stage_m):
            _drop("implausible_stage")
            continue
        cleaned.append((epoch, stage))

    # Sort by time; a later packet for a duplicate timestamp supersedes the earlier one.
    cleaned.sort(key=lambda p: p[0])
    deduped: list[tuple[float, float]] = []
    for epoch, stage in cleaned:
        if deduped and epoch == deduped[-1][0]:
            deduped[-1] = (epoch, stage)
            _drop("duplicate_timestamp")
        else:
            deduped.append((epoch, stage))

    warnings: list[str] = []
    n_dropped = n_input - len(deduped)

    if not deduped:
        # No usable reading is itself a liveness signal: with an as_of, that is a dead
        # or absent gauge, not merely an unknown one.
        return GaugeSeries(
            times_s=np.empty(0),
            stage_m=np.empty(0),
            origin_utc=None,
            sensor_alive=(False if as_of is not None else None),
            n_input=n_input,
            n_dropped=n_dropped,
            dropped=dropped,
            median_interval_s=None,
            warnings=("no valid samples after cleaning",),
        )

    epochs = np.array([p[0] for p in deduped], dtype=float)
    stage_m = np.array([p[1] for p in deduped], dtype=float)
    origin_epoch = float(epochs[0])
    times_s = epochs - origin_epoch
    origin_utc = datetime.fromtimestamp(origin_epoch, tz=UTC)

    median_interval_s: float | None = None
    if epochs.size >= 2:
        diffs = np.diff(epochs)
        median_interval_s = float(np.median(diffs))
        if median_interval_s > 2 * cfg.expected_sample_interval_s:
            warnings.append(
                f"median sampling {median_interval_s:.0f} s is much coarser than the "
                f"expected {cfg.expected_sample_interval_s:.0f} s; rate-of-rise will be "
                f"under-resolved"
            )
        largest_gap = float(diffs.max())
        if largest_gap > cfg.staleness_factor * cfg.expected_sample_interval_s:
            warnings.append(
                f"internal gap of {largest_gap:.0f} s exceeds the staleness threshold; "
                f"the gauge dropped out mid-series"
            )

    # Liveness against the ingestion time: did the expected next packet arrive?
    sensor_alive: bool | None = None
    if as_of is not None:
        age_s = _to_epoch_s(as_of) - float(epochs[-1])
        staleness_limit = cfg.staleness_factor * cfg.expected_sample_interval_s
        sensor_alive = age_s <= staleness_limit
        if not sensor_alive:
            warnings.append(
                f"newest sample is {age_s:.0f} s old (> {staleness_limit:.0f} s); "
                f"sensor declared dead"
            )

    return GaugeSeries(
        times_s=times_s,
        stage_m=stage_m,
        origin_utc=origin_utc,
        sensor_alive=sensor_alive,
        n_input=n_input,
        n_dropped=n_dropped,
        dropped=dropped,
        median_interval_s=median_interval_s,
        warnings=tuple(warnings),
    )


def parse_csv(
    text: str,
    *,
    delimiter: str = ",",
    has_header: bool = True,
    time_format: str | None = None,
) -> tuple[list[datetime], list[float]]:
    """Parse a two-column ``timestamp,stage`` export into ingest-ready lists.

    The tabular shape a DHM logger export takes. Timestamps are parsed as timezone-aware
    datetimes; a row whose timestamp is naive is rejected here rather than silently
    assumed to be Nepal time. Rows that do not parse are skipped and their count is
    recoverable by comparing the returned length to the input line count.

    Args:
        time_format: a ``strptime`` format; if omitted, ISO 8601 (``fromisoformat``) is
            used. Either way the result must be timezone-aware.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if has_header and lines:
        lines = lines[1:]

    timestamps: list[datetime] = []
    values: list[float] = []
    for line in lines:
        parts = line.split(delimiter)
        if len(parts) < 2:
            continue
        raw_ts, raw_val = parts[0].strip(), parts[1].strip()
        try:
            ts = (
                datetime.strptime(raw_ts, time_format)
                if time_format is not None
                else datetime.fromisoformat(raw_ts)
            )
            val = float(raw_val)
        except ValueError:
            continue
        if ts.tzinfo is None:
            raise ValueError(
                f"naive timestamp {raw_ts!r} in export; DHM timestamps must carry an "
                f"explicit UTC+05:45 offset, never an assumed one"
            )
        timestamps.append(ts)
        values.append(val)
    return timestamps, values
