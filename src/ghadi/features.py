"""Discriminant features for the mass-movement / earthquake / noise decision.

Every feature encodes one physical difference and a developer must be able to say
which (HANDOFF §5.2). Reading "EQ -> mass movement":

- ``emergence_s``: extended slow source ramps up, rupture jumps. small -> large
- ``kurtosis``: impulsiveness of the amplitude distribution. high -> low
- ``spectral_ratio_low_high``: low-stress-drop extended source is HF-depleted.
  low -> **high**
- ``spectral_centroid_hz``: the same physics as a first moment. higher -> **lower**
- ``duration_80_s``: long-duration mass flux vs short body-wave train. low -> high
- ``rise_to_duration``: envelope shape, scale-free. small -> large

Experiment 001 found the two spectral features carried almost all the separation while
the temporal features were broken. Both defects are now repaired (M2):

- **Issue 2.1.** ``emergence_s`` is measured forward from the **trigger onset**, which
  the caller supplies. Measured against the *global window peak* it was meaningless
  whenever the peak was not the event, or the window was noise with no true peak
  (307 s for an earthquake, 254 s for noise). The broken version is retained as
  ``emergence_s_global_peak``, marked DEPRECATED, so Experiment 001 stays reproducible.
- **Issue 2.3.** ``duration_ratio`` rewarded energy spread evenly across the window,
  which is the definition of noise. It is now gated on signal presence.

**Issues 2.1 and 2.3 turned out to be one issue.** Measuring emergence from the onset
is necessary but not sufficient: on a window containing no event, 10% of the peak is
crossed at the first sample and 90% wherever the largest random fluctuation lands, so
noise still scored a *longer* emergence than a real arrival (52.8 s against 20.3 s on
the test fixtures). Emergence is therefore gated on signal presence as well, and both
it and ``duration_ratio`` are NaN when there is no signal.

NaN is deliberate throughout, and is not a gap to be filled with a default. A feature
that is undefined for an input must say so, or a model will learn from a number that
means nothing.

The dependency runs one way: ``detect`` imports ``features``, never the reverse. That
is why the onset is a parameter rather than something this module computes.

``Features.mass_movement_score`` from the reference skeleton is deliberately **absent**:
Experiment 001 showed it ranked noise above the actual target, and issue 3.6 requires it
never reach a model release. Do not reintroduce a hand-weighted composite here.

This module is on the detection path: numpy and scipy only, no obspy, no plotting.

"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import signal as sp_signal
from scipy import stats as sp_stats

from .config import DEFAULT, SeismicConfig


@dataclass(frozen=True)
class Features:
    """Discriminant features for one analysis window."""

    emergence_s: float  # NaN when no onset was supplied — emergence needs a reference
    kurtosis: float
    spectral_ratio_low_high: float
    spectral_centroid_hz: float
    duration_80_s: float
    duration_ratio: float  # NaN when no signal is present (issue 2.3)
    rise_to_duration: float
    peak_amplitude: float
    rms_amplitude: float
    signal_present: bool
    snr_ratio: float  # peak envelope over the median envelope; drives the gate
    emergence_s_global_peak: float = float("nan")  # DEPRECATED — kept for exp001 only
    meta: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, float]:
        return {
            "emergence_s": self.emergence_s,
            "kurtosis": self.kurtosis,
            "spectral_ratio_low_high": self.spectral_ratio_low_high,
            "spectral_centroid_hz": self.spectral_centroid_hz,
            "duration_80_s": self.duration_80_s,
            "duration_ratio": self.duration_ratio,
            "rise_to_duration": self.rise_to_duration,
            "peak_amplitude": self.peak_amplitude,
            "rms_amplitude": self.rms_amplitude,
            "snr_ratio": self.snr_ratio,
            "emergence_s_global_peak": self.emergence_s_global_peak,
        }


def preprocess(
    data: np.ndarray, sampling_rate: float, config: SeismicConfig | None = None
) -> np.ndarray:
    """Demean, taper and band-pass into the analysis band.

    The taper is a fixed number of seconds, not a fraction of the window. It exists
    only to suppress filter edge transients, and a few seconds does that at any
    window length; a fractional taper instead grows with the window and destroys the
    early samples that the LTA baseline is computed from (exp001).

    Instrument-response deconvolution is *not* done here — it is issue 2.4. Until it
    lands, features are in counts and are only comparable within one station.
    """
    config = config or DEFAULT.seismic
    if data.size == 0:
        raise ValueError("empty trace")

    x = np.asarray(data, dtype=float)
    x = x - x.mean()
    duration_s = x.size / sampling_rate
    # Tukey's alpha is the total tapered fraction, split between the two ends.
    alpha = min(2.0 * config.taper_s / duration_s, 1.0) if duration_s > 0 else 1.0
    x = x * sp_signal.windows.tukey(x.size, alpha=alpha)

    nyquist = 0.5 * sampling_rate
    low = config.band_hz[0] / nyquist
    high = min(config.band_hz[1] / nyquist, 0.99)
    if not 0 < low < high < 1:
        raise ValueError(f"invalid band {config.band_hz} for sampling rate {sampling_rate}")
    sos = sp_signal.butter(4, [low, high], btype="bandpass", output="sos")
    return np.asarray(sp_signal.sosfiltfilt(sos, x), dtype=float)


def envelope(data: np.ndarray) -> np.ndarray:
    """Amplitude envelope via the analytic signal."""
    return np.abs(sp_signal.hilbert(data)).astype(float)


def spectral_features(
    data: np.ndarray, sampling_rate: float, config: SeismicConfig | None = None
) -> tuple[float, float]:
    """Return ``(low/high energy ratio, spectral centroid Hz)``.

    A spatially extended, slow, low-stress-drop source radiates low-frequency energy;
    a sharp tectonic rupture does not. This is the separation GHADI is built on: the
    2026 cascade sits at ratio 13.65 / centroid 1.44 Hz against 0.87-4.74 / 2.76-3.85 Hz
    for real earthquakes and noise on the same station.
    """
    config = config or DEFAULT.seismic
    freqs, psd = sp_signal.welch(
        data, fs=sampling_rate, nperseg=min(len(data), int(sampling_rate * 20))
    )
    band = (freqs >= config.band_hz[0]) & (freqs <= config.band_hz[1])
    freqs, psd = freqs[band], psd[band]
    if psd.sum() <= 0:
        return float("nan"), float("nan")

    low = psd[freqs < config.spectral_split_hz].sum()
    high = psd[freqs >= config.spectral_split_hz].sum()
    ratio = float(low / high) if high > 0 else float("inf")
    centroid = float((freqs * psd).sum() / psd.sum())
    return ratio, centroid


def _duration_80(env: np.ndarray, sampling_rate: float) -> tuple[float, float]:
    """Time spanning the central 80% of cumulative envelope energy, and rise time.

    Returns ``(duration_80_s, rise_s)`` where rise is 5% -> peak within that span.
    """
    cumulative = np.cumsum(env)
    total = cumulative[-1]
    if total <= 0:
        return 0.0, 0.0
    fraction = cumulative / total
    i5 = int(np.searchsorted(fraction, 0.10))
    i95 = int(np.searchsorted(fraction, 0.90))
    duration = max(i95 - i5, 0) / sampling_rate
    peak_index = int(np.argmax(env))
    rise = max(peak_index - i5, 0) / sampling_rate
    return float(duration), float(rise)


def _emergence_from_onset(
    env: np.ndarray, sampling_rate: float, onset_s: float, search_s: float
) -> float:
    """Issue 2.1. Rise time from 10% to 90% of the peak of *this arrival*.

    An extended, slow source ramps up; a rupture jumps. Measuring that ramp requires
    knowing where the signal starts, which is why the onset is supplied by the caller
    rather than guessed from the window maximum — the mistake that made the original
    feature report 307 s for an earthquake and 254 s for noise.

    The forward search is bounded by ``search_s``. Two reasons, one physical and one
    operational. Physically, emergence is a property of an arrival, not of everything
    that happens afterwards: unbounded, a small early trigger followed by a larger
    later one yields a rise time spanning the gap between them, which is not a ramp.
    Operationally, the bound is what keeps the feature causal — in real time you act
    on the trigger in front of you and cannot know which of a window's triggers will
    turn out to be the largest.

    Returns NaN if the onset falls outside the window or nothing rises after it.
    """
    onset_index = round(onset_s * sampling_rate)
    if onset_index < 0 or onset_index >= env.size - 1:
        return float("nan")

    end_index = min(onset_index + round(search_s * sampling_rate), env.size)
    after = env[onset_index:end_index]
    if after.size < 2:
        return float("nan")
    peak = float(after.max())
    if peak <= 0:
        return float("nan")

    above_10 = np.flatnonzero(after >= 0.10 * peak)
    above_90 = np.flatnonzero(after >= 0.90 * peak)
    if above_10.size == 0 or above_90.size == 0:
        return float("nan")
    return float((above_90[0] - above_10[0]) / sampling_rate)


def _emergence_global_peak(env: np.ndarray, sampling_rate: float) -> float:
    """DEPRECATED (issue 2.1). 10% -> 90% rise time measured against the GLOBAL peak.

    Kept only so Experiment 001 remains reproducible. It is meaningless when the window
    maximum is not the event, which is exactly the noise and earthquake cases.
    """
    peak = float(env.max())
    if peak <= 0:
        return float("nan")
    above_10 = np.flatnonzero(env >= 0.10 * peak)
    above_90 = np.flatnonzero(env >= 0.90 * peak)
    if above_10.size == 0 or above_90.size == 0:
        return float("nan")
    return float((above_90[0] - above_10[0]) / sampling_rate)


def signal_presence(env: np.ndarray, config: SeismicConfig | None = None) -> tuple[bool, float]:
    """Issue 2.3. Is there an event in this window at all?

    Peak envelope over median envelope. Diffuse noise sits near 1; a transient pushes
    it up. Returns ``(present, ratio)`` so the ratio can be inspected and the threshold
    re-tuned against a real corpus rather than trusted on faith.
    """
    config = config or DEFAULT.seismic
    median = float(np.median(env))
    if median <= 0:
        return False, float("nan")
    ratio = float(env.max()) / median
    return ratio >= config.signal_presence_ratio, ratio


def extract(
    data: np.ndarray,
    sampling_rate: float,
    config: SeismicConfig | None = None,
    preprocessed: bool = False,
    onset_s: float | None = None,
    segment_s: float | None = None,
) -> Features:
    """Extract the full discriminant feature set from one analysis window.

    Args:
        onset_s: trigger onset in seconds from the window start, from a detector.
            Required for ``emergence_s``; without it that feature is NaN, because
            emergence measured against the window maximum is the defect issue 2.1
            exists to fix. Callers on the detection path run the detector first and
            pass its onset through.

        segment_s: restrict every feature to ``segment_s`` seconds from the onset.
            This is what an operational detector can actually compute: a feature using
            more post-onset data than the decision allows is unavailable when the alert
            must fire, and training on whole windows while serving on segments is
            train/serve skew with a safety cost (exp005). Requires ``onset_s``.

    Latency budget: < 1 s per 240 s window on CPU (HANDOFF §5.1).
    """
    config = config or DEFAULT.seismic
    x = np.asarray(data, dtype=float) if preprocessed else preprocess(data, sampling_rate, config)

    if segment_s is not None:
        if onset_s is None:
            raise ValueError(
                "segment_s requires onset_s: a segment is measured from an arrival, "
                "and without one there is nothing to measure it from"
            )
        start = max(round(onset_s * sampling_rate), 0)
        stop = min(start + round(segment_s * sampling_rate), x.size)
        if stop - start < 2:
            raise ValueError(
                f"segment [{onset_s:.1f}s, +{segment_s:.1f}s] falls outside a "
                f"{x.size / sampling_rate:.1f}s window"
            )
        x = x[start:stop]
        # Features are now relative to the segment, so the arrival is at its start.
        onset_s = 0.0

    env = envelope(x)

    present, snr_ratio = signal_presence(env, config)
    ratio, centroid = spectral_features(x, sampling_rate, config)
    duration_80, rise = _duration_80(env, sampling_rate)
    window_s = len(x) / sampling_rate

    # Issue 2.3: duration-based features are gated on signal presence. Ungated, they
    # score highest on energy spread evenly across the window, which is exactly noise.
    duration_ratio = float(duration_80 / window_s) if (present and window_s > 0) else float("nan")

    # Emergence needs BOTH an onset and an actual signal. Issue 2.1 (measure from the
    # onset) is necessary but not sufficient: on a window with no event, "10% of the
    # peak" is crossed at the first sample and "90%" wherever the largest random
    # fluctuation happens to fall, so pure noise scores an emergence of roughly half
    # the remaining window — still beating a real event. Measured directly on the test
    # fixtures: 52.8 s for noise against 20.3 s for a genuine emergent arrival.
    emergence = (
        _emergence_from_onset(env, sampling_rate, onset_s, config.emergence_search_s)
        if (onset_s is not None and present)
        else float("nan")
    )

    return Features(
        emergence_s=emergence,
        kurtosis=float(sp_stats.kurtosis(x, fisher=False)),
        spectral_ratio_low_high=ratio,
        spectral_centroid_hz=centroid,
        duration_80_s=duration_80,
        duration_ratio=duration_ratio,
        rise_to_duration=float(rise / duration_80) if duration_80 > 0 else float("nan"),
        peak_amplitude=float(np.abs(x).max()),
        rms_amplitude=float(np.sqrt(np.mean(x**2))),
        signal_present=present,
        snr_ratio=snr_ratio,
        emergence_s_global_peak=_emergence_global_peak(env, sampling_rate),
        meta={"window_s": window_s, "sampling_rate": sampling_rate},
    )
