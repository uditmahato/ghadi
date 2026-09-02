"""The baseline detector, and the artefact guard that every developer hits."""

from __future__ import annotations

import numpy as np
import pytest

from ghadi.config import DEFAULT
from ghadi.detect import sta_lta, sta_lta_ratio


def test_no_trigger_survives_the_settling_boundary(
    noise_window: np.ndarray, emergent_window: np.ndarray, sampling_rate: float
) -> None:
    """HANDOFF §2.2 Finding 5 / issue 2.2.

    Every window produced a spurious trigger at the settling boundary because the LTA
    had not settled. Nothing may fire inside the discarded region.
    """
    settling_s = DEFAULT.seismic.lta_s + DEFAULT.seismic.taper_s
    for window in (noise_window, emergent_window):
        result = sta_lta(window, sampling_rate)
        assert result.settling_s == settling_s
        for trigger in result.triggers:
            assert trigger.on_s > settling_s, (
                f"trigger at {trigger.on_s:.1f}s is inside the {settling_s:.0f}s "
                "settling region — this is the artefact, not a detection"
            )


def test_settling_region_is_nan_not_a_number(
    noise_window: np.ndarray, sampling_rate: float
) -> None:
    ratio, times = sta_lta_ratio(noise_window, sampling_rate)
    settling = times < DEFAULT.seismic.lta_s + DEFAULT.seismic.taper_s
    assert np.all(np.isnan(ratio[settling]))
    assert np.any(np.isfinite(ratio[~settling]))


def test_taper_does_not_scale_with_window_length(sampling_rate: float) -> None:
    """The taper must be a fixed few seconds, not a fraction of the window.

    Experiment 001: a fractional taper (alpha=0.05) on a 35-minute window suppressed
    52 s of samples at each end. Those suppressed samples sit inside the LTA's
    trailing window and manufacture a trigger the moment the STA clears the taper.
    Assert the tapered fraction shrinks as the window grows.
    """
    from ghadi.features import preprocess

    rng = np.random.default_rng(101)
    tapered_fractions = []
    for duration_s in (240.0, 2100.0):
        n = int(duration_s * sampling_rate)
        flat = np.ones(n) + rng.normal(0, 0.001, n)
        out = np.abs(preprocess(flat, sampling_rate))
        # Fraction of the leading half whose amplitude is visibly suppressed.
        half = out[: n // 2]
        suppressed = int(np.sum(half < 0.5 * np.median(half)))
        tapered_fractions.append(suppressed / n)

    assert tapered_fractions[1] < tapered_fractions[0], (
        "tapered fraction did not shrink with a longer window — the taper is still "
        "length-proportional and will corrupt the LTA baseline"
    )


def test_emergent_event_triggers_near_its_onset(
    emergent_window: np.ndarray, sampling_rate: float
) -> None:
    result = sta_lta(emergent_window, sampling_rate)
    assert result.triggers, "the emergent event should produce at least one trigger"
    first = result.first_trigger
    assert first is not None
    # Onset is at t=120 s with a 25 s ramp; an emergent arrival is detected late by
    # construction, which is exactly why STA/LTA is only the baseline.
    assert 115.0 < first.on_s < 175.0


def test_quiet_noise_does_not_trigger(noise_window: np.ndarray, sampling_rate: float) -> None:
    result = sta_lta(noise_window, sampling_rate)
    assert not result.triggers
    assert result.max_ratio < DEFAULT.seismic.trigger_on


def test_event_window_has_a_higher_peak_ratio_than_noise(
    noise_window: np.ndarray, impulsive_window: np.ndarray, sampling_rate: float
) -> None:
    assert (
        sta_lta(impulsive_window, sampling_rate).max_ratio
        > sta_lta(noise_window, sampling_rate).max_ratio
    )


def test_window_shorter_than_the_lta_is_refused(sampling_rate: float) -> None:
    short = np.random.default_rng(5).normal(0, 1, int(30 * sampling_rate))
    with pytest.raises(ValueError, match="shorter than"):
        sta_lta(short, sampling_rate)


def test_classifier_refuses_to_pretend_it_exists(
    emergent_window: np.ndarray, sampling_rate: float
) -> None:
    from ghadi.detect.classify import classify
    from ghadi.features import extract

    with pytest.raises(NotImplementedError, match="M3"):
        classify(extract(emergent_window, sampling_rate))
