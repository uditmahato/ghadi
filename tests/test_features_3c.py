"""Three-component polarisation discriminants (issue 2.5).

Each test states the physics it encodes. The synthetic signals are idealised — a real
arrival is never this clean — so these verify the *mechanics* of the descriptors, not
that they separate real classes. That measurement needs a three-component corpus and
has not been made.
"""

from __future__ import annotations

import numpy as np
import pytest

from ghadi.features_3c import hv_ratio, polarisation, polarisation_over_window

SR = 50.0
N = int(20 * SR)


def _t() -> np.ndarray:
    return np.arange(N) / SR


def vertical_p_wave() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A steeply-incident P arrival: nearly all motion along the vertical."""
    rng = np.random.default_rng(3)
    wave = np.sin(2 * np.pi * 5.0 * _t()) * np.exp(-_t() / 3.0)
    z = 100.0 * wave + rng.normal(0, 0.5, N)
    n = 3.0 * wave + rng.normal(0, 0.5, N)
    e = 3.0 * wave + rng.normal(0, 0.5, N)
    return z, n, e


def surface_wave() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A Rayleigh-like arrival: elliptical, horizontal-rich, quarter-cycle lag."""
    rng = np.random.default_rng(5)
    t = _t()
    envelope = np.exp(-t / 8.0)
    z = 40.0 * np.sin(2 * np.pi * 1.5 * t) * envelope + rng.normal(0, 0.5, N)
    n = 80.0 * np.cos(2 * np.pi * 1.5 * t) * envelope + rng.normal(0, 0.5, N)
    e = 60.0 * np.cos(2 * np.pi * 1.5 * t) * envelope + rng.normal(0, 0.5, N)
    return z, n, e


def isotropic_noise() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(7)
    return rng.normal(0, 1, N), rng.normal(0, 1, N), rng.normal(0, 1, N)


# --- H/V ----------------------------------------------------------------------------


def test_surface_wave_is_more_horizontal_than_a_body_wave() -> None:
    """A surface process is an efficient generator of surface waves and an
    inefficient one of body waves, so it puts proportionally more energy on the
    horizontal components."""
    assert hv_ratio(*surface_wave()) > hv_ratio(*vertical_p_wave())


def test_steeply_incident_p_wave_has_low_hv() -> None:
    assert hv_ratio(*vertical_p_wave()) < 1.0


def test_hv_of_a_dead_vertical_channel_is_nan_not_infinite() -> None:
    zeros = np.zeros(N)
    ones = np.ones(N)
    assert np.isnan(hv_ratio(zeros, ones, ones))


# --- polarisation -------------------------------------------------------------------


def test_a_linear_arrival_is_rectilinear_and_noise_is_not() -> None:
    """Rectilinearity separates organised particle motion from isotropic noise —
    a different axis entirely from spectral content, which is the point of adding it
    (exp003: the two spectral features encode one idea and fail together)."""
    assert polarisation(*vertical_p_wave()).rectilinearity > 0.8
    assert polarisation(*isotropic_noise()).rectilinearity < 0.3


def test_vertical_arrival_has_a_small_incidence_angle() -> None:
    # Incidence measured from vertical: a wave arriving from below is near 0.
    assert polarisation(*vertical_p_wave()).incidence_deg < 20.0


def test_surface_wave_has_a_large_incidence_angle() -> None:
    assert polarisation(*surface_wave()).incidence_deg > 45.0


def test_components_must_be_the_same_length() -> None:
    with pytest.raises(ValueError, match="same length"):
        polarisation(np.zeros(10), np.zeros(9), np.zeros(10))


def test_too_few_samples_is_refused() -> None:
    with pytest.raises(ValueError, match="at least two samples"):
        polarisation(np.zeros(1), np.zeros(1), np.zeros(1))


def test_a_silent_stream_yields_nan_rather_than_a_fabricated_angle() -> None:
    zeros = np.zeros(N)
    result = polarisation(zeros, zeros, zeros)
    assert np.isnan(result.rectilinearity)
    assert np.isnan(result.incidence_deg)


# --- windowing ----------------------------------------------------------------------


def test_windowed_polarisation_isolates_the_arrival() -> None:
    """Averaged over a whole window, polarisation collapses toward the isotropic value
    of whatever noise dominates. Bounding it to the arrival is what makes it a
    descriptor of the arrival — the same lesson as exp002's emergence bound."""
    rng = np.random.default_rng(11)
    long_n = int(120 * SR)
    z = rng.normal(0, 1, long_n)
    n = rng.normal(0, 1, long_n)
    e = rng.normal(0, 1, long_n)

    onset = 60.0
    i0 = int(onset * SR)
    pz, pn, pe = vertical_p_wave()
    z[i0 : i0 + N] += pz
    n[i0 : i0 + N] += pn
    e[i0 : i0 + N] += pe

    windowed = polarisation_over_window(z, n, e, SR, onset_s=onset, duration_s=20.0)
    whole = polarisation(z, n, e)
    assert windowed.rectilinearity > whole.rectilinearity


def test_a_window_past_the_end_yields_nan() -> None:
    z, n, e = vertical_p_wave()
    result = polarisation_over_window(z, n, e, SR, onset_s=10_000.0)
    assert np.isnan(result.rectilinearity)
