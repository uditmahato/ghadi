"""The honest baseline. Every learned model must beat this.

Classical recursive-free STA/LTA over the envelope of a band-passed trace.

**The settling artefact (HANDOFF §2.2, Finding 5).** Every window produces a spurious
trigger shortly after the start because the long-term average has not yet settled: for
the first LTA-length of a window the LTA is computed over fewer samples than it needs
and is biased low, so the ratio spikes. This is not a detection.

Experiment 001 showed the contaminated region is **taper + LTA**, not LTA alone: the
preprocessing taper suppresses the earliest samples, and those suppressed samples sit
inside the LTA's trailing window for a further ``taper_s`` seconds after the taper
itself has ended. Discarding only ``lta_s`` leaves a trigger standing at ``lta_s + ε``
on real data. Both are handled — the taper is now a fixed few seconds (see
``ghadi.features.preprocess``) *and* the guard covers ``taper_s + lta_s``.

Do not "fix" a surviving edge trigger by lowering the threshold, and never let one
into a training set as a positive.

Latency budget: < 100 ms (HANDOFF §5.1).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import DEFAULT, SeismicConfig
from ..features import envelope, preprocess


@dataclass(frozen=True)
class Trigger:
    """One STA/LTA trigger, in seconds from the start of the window."""

    on_s: float
    off_s: float
    peak_ratio: float

    @property
    def duration_s(self) -> float:
        return self.off_s - self.on_s


@dataclass(frozen=True)
class StaLtaResult:
    ratio: np.ndarray  # NaN inside the discarded settling region
    times_s: np.ndarray
    triggers: tuple[Trigger, ...]
    settling_s: float
    sampling_rate: float

    @property
    def max_ratio(self) -> float:
        finite = self.ratio[np.isfinite(self.ratio)]
        return float(finite.max()) if finite.size else float("nan")

    @property
    def first_trigger(self) -> Trigger | None:
        return self.triggers[0] if self.triggers else None


def sta_lta_ratio(
    data: np.ndarray,
    sampling_rate: float,
    config: SeismicConfig | None = None,
    preprocessed: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(ratio, times_s)``; the settling region is NaN, never a number."""
    config = config or DEFAULT.seismic
    x = np.asarray(data, dtype=float) if preprocessed else preprocess(data, sampling_rate, config)
    env = envelope(x)
    power = env**2

    n_sta = max(round(config.sta_s * sampling_rate), 1)
    n_lta = max(round(config.lta_s * sampling_rate), n_sta + 1)
    n_settle = n_lta + max(round(config.taper_s * sampling_rate), 0)
    if power.size <= n_settle:
        raise ValueError(
            f"window of {power.size / sampling_rate:.1f} s is shorter than the "
            f"{config.lta_s + config.taper_s:.0f} s settling region "
            f"({config.lta_s:.0f} s LTA + {config.taper_s:.0f} s taper) — "
            "nothing can be detected in it"
        )

    cumulative = np.concatenate([[0.0], np.cumsum(power)])

    def trailing_mean(n: int) -> np.ndarray:
        out = np.full(power.size, np.nan)
        out[n:] = (cumulative[n:-1] - cumulative[: -n - 1]) / n
        return out

    sta = trailing_mean(n_sta)
    lta = trailing_mean(n_lta)

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(lta > 0, sta / lta, np.nan)

    # Discard taper + LTA: until then the LTA's trailing window still contains
    # taper-suppressed samples, so the ratio is biased high and not meaningful.
    ratio[:n_settle] = np.nan

    times = np.arange(power.size) / sampling_rate
    return ratio, times


def sta_lta(
    data: np.ndarray,
    sampling_rate: float,
    config: SeismicConfig | None = None,
    preprocessed: bool = False,
) -> StaLtaResult:
    """Run the baseline detector over one window."""
    config = config or DEFAULT.seismic
    ratio, times = sta_lta_ratio(data, sampling_rate, config, preprocessed)

    triggers: list[Trigger] = []
    on_index: int | None = None
    for i, value in enumerate(ratio):
        if not np.isfinite(value):
            continue
        if on_index is None:
            if value >= config.trigger_on:
                on_index = i
        elif value <= config.trigger_off:
            segment = ratio[on_index : i + 1]
            triggers.append(
                Trigger(
                    on_s=float(times[on_index]),
                    off_s=float(times[i]),
                    peak_ratio=float(np.nanmax(segment)),
                )
            )
            on_index = None

    if on_index is not None:  # still open at the end of the window
        segment = ratio[on_index:]
        triggers.append(
            Trigger(
                on_s=float(times[on_index]),
                off_s=float(times[-1]),
                peak_ratio=float(np.nanmax(segment)),
            )
        )

    return StaLtaResult(
        ratio=ratio,
        times_s=times,
        triggers=tuple(triggers),
        settling_s=config.lta_s + config.taper_s,
        sampling_rate=sampling_rate,
    )
