"""Gauge anomaly detection, including the destroyed-sensor case that actually happened."""

from __future__ import annotations

import numpy as np

from ghadi.config import DEFAULT
from ghadi.hydro import detect_anomaly, rate_of_rise, robust_z, synthetic_surge


def test_flat_river_produces_no_anomaly() -> None:
    times = np.arange(0.0, 3600.0, 60.0)
    stage = np.full_like(times, 2.0) + np.random.default_rng(7).normal(0, 0.01, times.size)
    result = detect_anomaly(times, stage)
    assert not result.detected


def test_trishuli_scale_surge_is_detected() -> None:
    # ~9 m in 30 minutes, the observed 26 August 2026 progression.
    times, stage = synthetic_surge()
    result = detect_anomaly(times, stage)
    assert result.detected
    assert result.peak_rate_m_per_min > DEFAULT.hydro.rate_threshold_m_per_min


def test_detection_precedes_the_full_rise() -> None:
    # The value of rate-of-rise over an absolute stage threshold is that it fires on
    # the leading edge, not after the water has already arrived.
    times, stage = synthetic_surge(surge_start_s=1200.0, surge_rise_s=1800.0)
    result = detect_anomaly(times, stage)
    assert result.detected and result.time_s is not None
    assert result.time_s < 1200.0 + 1800.0


def test_destroyed_sensor_still_yields_a_detection() -> None:
    """Four of five gauges were destroyed by the surge before their absolute stage
    thresholds were crossed. A truncated series is the normal case, not an edge case."""
    times, stage = synthetic_surge(destroy_at_s=2100.0)
    result = detect_anomaly(times, stage)
    assert result.detected, "the sensor died mid-surge but had already seen the rise"
    assert times[-1] <= 2100.0


def test_sensor_destroyed_before_the_surge_reports_honestly() -> None:
    times, stage = synthetic_surge(destroy_at_s=600.0)
    result = detect_anomaly(times, stage)
    assert not result.detected
    assert "below" in result.reason  # says why, does not silently return False


def test_series_too_short_is_flagged_as_truncated() -> None:
    result = detect_anomaly(np.array([0.0, 60.0]), np.array([2.0, 2.1]))
    assert not result.detected
    assert result.truncated
    assert "too short" in result.reason


def test_rate_of_rise_matches_a_hand_computed_ramp() -> None:
    # 1 m over 10 minutes = 0.1 m/min.
    times = np.arange(0.0, 601.0, 60.0)
    stage = 2.0 + times * (1.0 / 600.0)
    rates = rate_of_rise(times, stage, window_s=300.0)
    assert np.isclose(rates[-1], 0.1, atol=1e-6)


def test_robust_z_is_unmoved_by_a_single_outlier() -> None:
    values = np.concatenate([np.zeros(99), np.array([1000.0])])
    z = robust_z(values)
    assert abs(float(np.median(z))) < 1e-9
    assert z[-1] > 50.0


def test_a_flat_gauge_with_one_excursion_still_scores_it() -> None:
    """A quiet gauge sits at a constant stage, so the MAD degenerates to zero.

    The fallback scale must keep a single excursion visible — otherwise the z
    channel goes silent on precisely the rivers where it is most needed.
    """
    values = np.concatenate([np.full(50, 0.01), np.array([0.9])])
    z = robust_z(values)
    assert z[-1] > 10.0, "a lone excursion on a flat baseline must not score zero"


def test_robust_z_of_a_constant_series_is_zero_not_nan() -> None:
    assert np.all(robust_z(np.full(50, 3.0)) == 0.0)
