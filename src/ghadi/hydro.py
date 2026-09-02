"""Gauge rate-of-rise anomaly detection, and a synthetic surge generator for testing.

The detector deliberately takes a plain ``(times_s, stage_m)`` pair rather than a DHM
client object, because DHM telemetry access is an open negotiation (Blocker B2). Swap
the loader, keep the detector — a refusal delays fusion, it does not kill the project.

Reference figure for calibration: the Trishuli rose ~9 m in 30 minutes on 26 August
2026, i.e. ~0.30 m/min sustained with a far steeper leading edge. The default absolute
threshold of 0.20 m/min sits below that.

**Sensor mortality is data, not missingness.** Four of five downstream gauges were
destroyed by the surge before their absolute stage thresholds were crossed. The
synthetic generator therefore supports ``destroy_at_s``, and every hydro detector is
tested against a destroyed sensor because that is what actually happened.

Latency budget: < 100 ms. Detection path — numpy only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import DEFAULT, HydroConfig


@dataclass(frozen=True)
class HydroAnomaly:
    """Rate-of-rise anomaly on one gauge."""

    detected: bool
    time_s: float | None  # when the anomaly was first flagged
    peak_rate_m_per_min: float
    robust_z: float
    reason: str
    n_samples: int
    truncated: bool  # series ends early => the sensor probably died


def rate_of_rise(
    times_s: np.ndarray, stage_m: np.ndarray, window_s: float | None = None
) -> np.ndarray:
    """Rate of rise in m/min, estimated over a trailing window.

    Uses a trailing difference rather than a point derivative so a single noisy
    sample cannot fire the detector.
    """
    window_s = window_s if window_s is not None else DEFAULT.hydro.rate_window_s
    times = np.asarray(times_s, dtype=float)
    stage = np.asarray(stage_m, dtype=float)
    if times.size != stage.size:
        raise ValueError("times_s and stage_m must be the same length")
    if times.size < 2:
        return np.zeros_like(stage)

    rates = np.zeros_like(stage)
    for i in range(1, times.size):
        j = int(np.searchsorted(times, times[i] - window_s, side="left"))
        j = min(j, i - 1)
        dt_min = (times[i] - times[j]) / 60.0
        rates[i] = (stage[i] - stage[j]) / dt_min if dt_min > 0 else 0.0
    return rates


def robust_z(values: np.ndarray) -> np.ndarray:
    """Median/MAD z-score. Robust to the surge itself contaminating the baseline."""
    values = np.asarray(values, dtype=float)
    median = float(np.median(values))
    deviations = np.abs(values - median)
    scale = 1.4826 * float(np.median(deviations))

    if scale <= 0:
        # The MAD degenerates to zero whenever more than half the samples are
        # identical — which is exactly a quiet gauge sitting at a constant stage
        # between events. Scoring everything zero there would erase the one
        # excursion we exist to catch, so fall back to the mean absolute deviation.
        scale = float(deviations.mean())

    if scale <= 0:
        return np.zeros_like(values)  # genuinely constant: no excursion to score
    return (values - median) / scale


def detect_anomaly(
    times_s: np.ndarray,
    stage_m: np.ndarray,
    config: HydroConfig | None = None,
) -> HydroAnomaly:
    """Flag a rate-of-rise anomaly.

    Fires when the rate crosses the absolute threshold **or** the robust z-score of
    the rate crosses its threshold. Absolute-only would miss a small-but-anomalous
    river; z-only would fire on a quiet gauge with a tiny MAD.
    """
    config = config or DEFAULT.hydro
    times = np.asarray(times_s, dtype=float)
    stage = np.asarray(stage_m, dtype=float)

    if times.size < 3:
        return HydroAnomaly(
            detected=False,
            time_s=None,
            peak_rate_m_per_min=0.0,
            robust_z=0.0,
            reason="series too short to estimate a rate",
            n_samples=int(times.size),
            truncated=True,
        )

    rates = rate_of_rise(times, stage, config.rate_window_s)
    z = robust_z(rates)

    absolute_hits = np.flatnonzero(rates >= config.rate_threshold_m_per_min)
    z_hits = np.flatnonzero(z >= config.robust_z_threshold)
    hits = np.union1d(absolute_hits, z_hits)

    peak_rate = float(rates.max())
    peak_z = float(z.max())

    if hits.size == 0:
        return HydroAnomaly(
            detected=False,
            time_s=None,
            peak_rate_m_per_min=peak_rate,
            robust_z=peak_z,
            reason=(
                f"peak rate {peak_rate:.3f} m/min below "
                f"{config.rate_threshold_m_per_min:.2f} and z {peak_z:.1f} below "
                f"{config.robust_z_threshold:.1f}"
            ),
            n_samples=int(times.size),
            truncated=False,
        )

    first = int(hits[0])
    triggered_by = []
    if first in set(absolute_hits.tolist()):
        triggered_by.append(f"absolute {rates[first]:.3f} m/min")
    if first in set(z_hits.tolist()):
        triggered_by.append(f"robust-z {z[first]:.1f}")

    return HydroAnomaly(
        detected=True,
        time_s=float(times[first]),
        peak_rate_m_per_min=peak_rate,
        robust_z=peak_z,
        reason="; ".join(triggered_by),
        n_samples=int(times.size),
        truncated=False,
    )


def synthetic_surge(
    duration_s: float = 3600.0,
    sample_interval_s: float = 60.0,
    baseline_m: float = 2.0,
    surge_start_s: float = 1200.0,
    surge_rise_m: float = 9.0,
    surge_rise_s: float = 1800.0,
    noise_m: float = 0.02,
    destroy_at_s: float | None = None,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a synthetic gauge series, optionally truncated by sensor death.

    Defaults reproduce the Trishuli reference figure: ~9 m over 30 minutes.

    Args:
        destroy_at_s: if given, the series is truncated here — the sensor was
            destroyed by the surge it was measuring. This is the normal case, not
            an edge case.
    """
    rng = np.random.default_rng(seed)
    times = np.arange(0.0, duration_s + sample_interval_s, sample_interval_s)

    # Logistic leading edge: steep front, then a plateau, which is the observed shape.
    midpoint = surge_start_s + surge_rise_s / 2.0
    steepness = 8.0 / surge_rise_s
    stage = baseline_m + surge_rise_m / (1.0 + np.exp(-steepness * (times - midpoint)))
    stage = stage + rng.normal(0.0, noise_m, size=times.size)

    if destroy_at_s is not None:
        alive = times <= destroy_at_s
        times, stage = times[alive], stage[alive]

    return times, stage
