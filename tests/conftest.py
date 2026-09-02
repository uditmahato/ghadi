"""Synthetic waveform fixtures.

These are *synthetic* signals used to test detector mechanics — onset timing, the
settling artefact, spectral ordering. They are not stand-ins for real waveforms and
no model is ever trained on them. Real-data regression against the four Experiment 001
cases lives in the experiment directory, which fetches and caches from EarthScope.
"""

from __future__ import annotations

import numpy as np
import pytest

SAMPLING_RATE = 50.0  # NK.KKN BHZ


def _noise(n: int, rng: np.random.Generator, scale: float = 1.0) -> np.ndarray:
    return rng.normal(0.0, scale, size=n)


@pytest.fixture
def sampling_rate() -> float:
    return SAMPLING_RATE


@pytest.fixture
def noise_window() -> np.ndarray:
    """240 s of stationary background noise. No event."""
    rng = np.random.default_rng(11)
    return _noise(int(240 * SAMPLING_RATE), rng)


@pytest.fixture
def emergent_window() -> np.ndarray:
    """240 s containing an emergent, low-frequency, long-duration arrival at t=120 s.

    Stands in for a mass movement: gradual ramp, energy concentrated near 1-2 Hz.
    """
    rng = np.random.default_rng(23)
    n = int(240 * SAMPLING_RATE)
    t = np.arange(n) / SAMPLING_RATE
    signal = _noise(n, rng, 0.5)

    onset = 120.0
    ramp = np.clip((t - onset) / 25.0, 0.0, 1.0)  # slow 25 s ramp-up
    decay = np.exp(-np.clip(t - (onset + 25.0), 0.0, None) / 90.0)  # long tail
    carrier = np.sin(2 * np.pi * 1.4 * t) + 0.6 * np.sin(2 * np.pi * 0.9 * t)
    return signal + 40.0 * ramp * decay * carrier


@pytest.fixture
def impulsive_window() -> np.ndarray:
    """240 s containing a sharp, high-frequency arrival at t=120 s.

    Stands in for a tectonic earthquake: near-instant onset, energy near 5-8 Hz.
    """
    rng = np.random.default_rng(37)
    n = int(240 * SAMPLING_RATE)
    t = np.arange(n) / SAMPLING_RATE
    signal = _noise(n, rng, 0.5)

    onset = 120.0
    envelope = np.where(t >= onset, np.exp(-(t - onset) / 8.0), 0.0)  # abrupt, short
    carrier = np.sin(2 * np.pi * 6.5 * t) + 0.7 * np.sin(2 * np.pi * 4.5 * t)
    return signal + 60.0 * envelope * carrier
