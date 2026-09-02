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
        "emergence_s",
        "kurtosis",
        "spectral_ratio_low_high",
        "spectral_centroid_hz",
        "duration_80_s",
        "duration_ratio",
        "rise_to_duration",
        "peak_amplitude",
        "rms_amplitude",
        "snr_ratio",
        "emergence_s_global_peak",
    }


# --- issue 2.1: emergence measured from the trigger onset ---------------------------


def test_emergence_is_nan_without_an_onset(
    emergent_window: np.ndarray, sampling_rate: float
) -> None:
    """Emergence is undefined without a reference point, and NaN says so.

    Returning the global-peak number instead is the exact defect issue 2.1 repairs:
    a model would learn from it without ever knowing it was meaningless.
    """
    assert np.isnan(extract(emergent_window, sampling_rate).emergence_s)


def test_emergent_source_ramps_slower_than_an_impulsive_one(
    emergent_window: np.ndarray, impulsive_window: np.ndarray, sampling_rate: float
) -> None:
    """The feature's whole purpose: an extended slow source ramps, a rupture jumps.

    Both fixtures place their arrival at t=120 s, so the onset is known exactly and
    the comparison isolates the ramp itself.
    """
    emergent = extract(emergent_window, sampling_rate, onset_s=120.0)
    impulsive = extract(impulsive_window, sampling_rate, onset_s=120.0)
    assert emergent.emergence_s > impulsive.emergence_s


def test_emergence_is_nan_on_noise_even_when_an_onset_is_supplied(
    emergent_window: np.ndarray, noise_window: np.ndarray, sampling_rate: float
) -> None:
    """exp001 Finding 4, and the reason issues 2.1 and 2.3 are actually one issue.

    Measuring from the onset instead of the global peak is necessary but not
    sufficient. On a window with no event, 10% of the peak is crossed at the first
    sample and 90% wherever the largest random fluctuation lands, so noise scored
    52.8 s against 20.3 s for a genuine emergent arrival — still the wrong ordering.
    The signal-presence gate is what makes the feature honest: no event, no emergence.
    """
    event = extract(emergent_window, sampling_rate, onset_s=120.0)
    noise = extract(noise_window, sampling_rate, onset_s=120.0)

    assert np.isfinite(event.emergence_s)
    assert np.isnan(noise.emergence_s), (
        "noise must not be assigned an emergence — it has no event to emerge"
    )


def test_onset_outside_the_window_yields_nan(
    emergent_window: np.ndarray, sampling_rate: float
) -> None:
    for bad_onset in (-5.0, 10_000.0):
        assert np.isnan(extract(emergent_window, sampling_rate, onset_s=bad_onset).emergence_s)


def test_a_later_larger_arrival_does_not_inflate_emergence(sampling_rate: float) -> None:
    """The forward search is bounded, and this is why (exp002).

    A small arrival followed much later by a larger one gave an unbounded search a
    'rise time' spanning the gap between two separate events: 287.9 s on a real
    earthquake window that happened to contain four triggers. Emergence is a property
    of one arrival, not of everything that follows it.

    The bound is also what makes the feature causal — in real time you act on the
    trigger in front of you and cannot know which later trigger will be largest.
    """
    from ghadi.config import DEFAULT

    rng = np.random.default_rng(71)
    n = int(600 * sampling_rate)
    t = np.arange(n) / sampling_rate
    signal = rng.normal(0, 0.5, n)

    for onset, amplitude, decay in ((120.0, 30.0, 6.0), (400.0, 300.0, 6.0)):
        env = np.where(t >= onset, np.exp(-(t - onset) / decay), 0.0)
        signal = signal + amplitude * env * np.sin(2 * np.pi * 6.0 * t)

    emergence = extract(signal, sampling_rate, onset_s=120.0).emergence_s
    assert emergence < DEFAULT.seismic.emergence_search_s, (
        "emergence spanned the gap to a later, larger arrival — the search is unbounded"
    )
    assert emergence < 60.0, f"emergence {emergence:.1f}s does not describe the first arrival"


# --- issue 2.3: duration features gated on signal presence --------------------------


def test_noise_is_not_marked_as_containing_a_signal(
    noise_window: np.ndarray, sampling_rate: float
) -> None:
    assert not extract(noise_window, sampling_rate).signal_present


def test_events_are_marked_as_containing_a_signal(
    emergent_window: np.ndarray, impulsive_window: np.ndarray, sampling_rate: float
) -> None:
    assert extract(emergent_window, sampling_rate).signal_present
    assert extract(impulsive_window, sampling_rate).signal_present


def test_duration_ratio_is_nan_on_noise(noise_window: np.ndarray, sampling_rate: float) -> None:
    """Ungated, duration_ratio scores highest on energy spread evenly across the
    window — which is the definition of noise, and is why exp001's composite ranked
    noise above the target."""
    assert np.isnan(extract(noise_window, sampling_rate).duration_ratio)


def test_duration_ratio_is_a_number_when_a_signal_is_present(
    emergent_window: np.ndarray, sampling_rate: float
) -> None:
    value = extract(emergent_window, sampling_rate).duration_ratio
    assert np.isfinite(value)
    assert 0.0 < value <= 1.0


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
