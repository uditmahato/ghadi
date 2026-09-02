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

As of Experiment 001 the two spectral features carry almost all the separation and the
temporal features are broken. Two known defects, both scheduled for M2:

- ``emergence_s`` is measured against the *global window peak*. When the peak is not
  the event — or the window is noise with no true peak — the number is meaningless
  (307 s for an earthquake, 254 s for noise). Issue 2.1 redefines it relative to the
  trigger onset. The broken version is kept as ``emergence_s_global_peak`` so
  Experiment 001 stays reproducible, and is marked DEPRECATED.
- ``duration_ratio`` rewards energy spread evenly across the window, which is the
  definition of noise. Issue 2.3 gates it on signal presence. Until then it is
  computed but must not be fed to a model.

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

    emergence_s_global_peak: float  # DEPRECATED — broken, see module docstring (M2)
    kurtosis: float
    spectral_ratio_low_high: float
    spectral_centroid_hz: float
    duration_80_s: float
    duration_ratio: float  # UNGATED — do not feed to a model before issue 2.3
    rise_to_duration: float
    peak_amplitude: float
    rms_amplitude: float
    meta: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, float]:
        return {
            "emergence_s_global_peak": self.emergence_s_global_peak,
            "kurtosis": self.kurtosis,
            "spectral_ratio_low_high": self.spectral_ratio_low_high,
            "spectral_centroid_hz": self.spectral_centroid_hz,
            "duration_80_s": self.duration_80_s,
            "duration_ratio": self.duration_ratio,
            "rise_to_duration": self.rise_to_duration,
            "peak_amplitude": self.peak_amplitude,
            "rms_amplitude": self.rms_amplitude,
        }


def preprocess(
    data: np.ndarray, sampling_rate: float, config: SeismicConfig | None = None
) -> np.ndarray:
    """Demean, taper and band-pass into the analysis band.

    Instrument-response deconvolution is *not* done here — it is issue 2.4. Until it
    lands, features are in counts and are only comparable within one station.
    """
    config = config or DEFAULT.seismic
    if data.size == 0:
        raise ValueError("empty trace")

    x = np.asarray(data, dtype=float)
    x = x - x.mean()
    x = x * sp_signal.windows.tukey(x.size, alpha=0.05)

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


def extract(
    data: np.ndarray,
    sampling_rate: float,
    config: SeismicConfig | None = None,
    preprocessed: bool = False,
) -> Features:
    """Extract the full discriminant feature set from one analysis window.

    Latency budget: < 1 s per 240 s window on CPU (HANDOFF §5.1).
    """
    config = config or DEFAULT.seismic
    x = np.asarray(data, dtype=float) if preprocessed else preprocess(data, sampling_rate, config)
    env = envelope(x)

    ratio, centroid = spectral_features(x, sampling_rate, config)
    duration_80, rise = _duration_80(env, sampling_rate)
    window_s = len(x) / sampling_rate

    return Features(
        emergence_s_global_peak=_emergence_global_peak(env, sampling_rate),
        kurtosis=float(sp_stats.kurtosis(x, fisher=False)),
        spectral_ratio_low_high=ratio,
        spectral_centroid_hz=centroid,
        duration_80_s=duration_80,
        duration_ratio=float(duration_80 / window_s) if window_s > 0 else float("nan"),
        rise_to_duration=float(rise / duration_80) if duration_80 > 0 else float("nan"),
        peak_amplitude=float(np.abs(x).max()),
        rms_amplitude=float(np.sqrt(np.mean(x**2))),
        meta={"window_s": window_s, "sampling_rate": sampling_rate},
    )
