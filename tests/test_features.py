"""Feature contracts. Each test states the physical difference the feature encodes."""

from __future__ import annotations

import numpy as np
import pytest

from ghadi import features
from ghadi.features import Features, extract, preprocess


def test_preprocess_removes_the_mean_and_the_band(sampling_rate: float) -> None:
    rng = np.random.default_rng(3)
    n = int(60 * sampling_rate)
    t = np.arange(n) / sampling_rate
    # A large DC offset plus a 24 Hz tone above the 20 Hz band edge.
    raw = 1000.0 + rng.normal(0, 1, n) + 50.0 * np.sin(2 * np.pi * 24.0 * t)
    out = preprocess(raw, sampling_rate)
    assert abs(float(out.mean())) < 1.0
    assert float(np.abs(out).max()) < float(np.abs(raw).max())


def test_preprocess_rejects_an_empty_trace(sampling_rate: float) -> None:
    with pytest.raises(ValueError, match="empty"):
        preprocess(np.array([]), sampling_rate)


def test_low_frequency_source_has_a_higher_lf_hf_ratio(
    emergent_window: np.ndarray, impulsive_window: np.ndarray, sampling_rate: float
) -> None:
    # The separation GHADI is built on: a spatially extended, slow, low-stress-drop
    # source radiates low-frequency energy; a sharp tectonic rupture does not.
    emergent = extract(emergent_window, sampling_rate)
    impulsive = extract(impulsive_window, sampling_rate)
    assert emergent.spectral_ratio_low_high > impulsive.spectral_ratio_low_high


def test_low_frequency_source_has_a_lower_spectral_centroid(
    emergent_window: np.ndarray, impulsive_window: np.ndarray, sampling_rate: float
) -> None:
    # The same physics expressed as a first moment. Experiment 001: 1.44 Hz for the
    # cascade against 2.76-3.85 Hz for earthquakes and noise.
    emergent = extract(emergent_window, sampling_rate)
    impulsive = extract(impulsive_window, sampling_rate)
    assert emergent.spectral_centroid_hz < impulsive.spectral_centroid_hz


def test_impulsive_source_is_more_kurtotic(
    emergent_window: np.ndarray, impulsive_window: np.ndarray, sampling_rate: float
) -> None:
    # Impulsiveness of the amplitude distribution.
    emergent = extract(emergent_window, sampling_rate)
    impulsive = extract(impulsive_window, sampling_rate)
    assert impulsive.kurtosis > emergent.kurtosis


def test_noise_is_far_less_kurtotic_than_any_event(
    noise_window: np.ndarray, impulsive_window: np.ndarray, sampling_rate: float
) -> None:
    assert (
        extract(noise_window, sampling_rate).kurtosis
        < extract(impulsive_window, sampling_rate).kurtosis
    )


def test_features_serialise_to_a_flat_dict(
    emergent_window: np.ndarray, sampling_rate: float
) -> None:
    values = extract(emergent_window, sampling_rate).as_dict()
    assert set(values) == {
        "emergence_s_global_peak",
        "kurtosis",
        "spectral_ratio_low_high",
        "spectral_centroid_hz",
        "duration_80_s",
        "duration_ratio",
        "rise_to_duration",
        "peak_amplitude",
        "rms_amplitude",
    }


def test_the_discredited_composite_score_is_absent() -> None:
    # Issue 3.6: Features.mass_movement_score ranked noise (0.823) above the actual
    # target (0.726) in Experiment 001. It must not reappear in any form.
    assert not hasattr(Features, "mass_movement_score")
    assert not hasattr(features, "mass_movement_score")


def test_broken_emergence_is_still_named_as_broken() -> None:
    # M2 (issue 2.1) redefines emergence relative to trigger onset. Until then the
    # global-peak version keeps its warning label so nobody mistakes it for the fix.
    assert "emergence_s_global_peak" in Features.__dataclass_fields__
    assert "DEPRECATED" in (features.__doc__ or "") or "DEPRECATED" in (
        features._emergence_global_peak.__doc__ or ""
    )
