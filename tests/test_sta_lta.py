"""The baseline detector, and the artefact guard that every developer hits."""

from __future__ import annotations

import numpy as np
import pytest

from ghadi.config import DEFAULT
from ghadi.detect import sta_lta, sta_lta_ratio


def test_no_trigger_survives_at_the_lta_settling_boundary(
    noise_window: np.ndarray, emergent_window: np.ndarray, sampling_rate: float
) -> None:
    """HANDOFF §2.2 Finding 5 / issue 2.2.

    Every window produced a spurious trigger at exactly +60 s because the 60 s LTA had
    not settled. The first LTA-length is discarded; nothing may fire there.
    """
    lta_s = DEFAULT.seismic.lta_s
    for window in (noise_window, emergent_window):
        result = sta_lta(window, sampling_rate)
        for trigger in result.triggers:
            assert trigger.on_s > lta_s, (
                f"trigger at {trigger.on_s:.1f}s is inside the {lta_s:.0f}s settling "
                "region — this is the artefact, not a detection"
            )


def test_settling_region_is_nan_not_a_number(
    noise_window: np.ndarray, sampling_rate: float
) -> None:
    ratio, times = sta_lta_ratio(noise_window, sampling_rate)
    settling = times < DEFAULT.seismic.lta_s
    assert np.all(np.isnan(ratio[settling]))
    assert np.any(np.isfinite(ratio[~settling]))


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
