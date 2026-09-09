"""The seismic physics detector: segment spectral features -> a mass-movement call.

This is deliberately **not** a learned classifier, and does not pretend to be one. The
positive class is n=1 (the 26 August 2026 cascade), so a supervised model cannot be
trained or validated honestly. What can be done honestly is a transparent decision rule,
and this is it:

    mass-movement-like  ==  (segment LF/HF >= cascade value)
                            AND (segment centroid <= cascade value)

A slow, low-frequency, extended source clears both thresholds. The thresholds are the
cascade's OWN decision-time-segment feature values (exp005). Three honesty constraints
are baked in rather than left to the caller:

1. It is a **conjunction of two per-feature thresholds, not a hand-weighted composite
   score** — a composite is forbidden (exp001 Finding 4, enforced in test_features.py).
2. A threshold at the target's own value is **fitted to one event and is a lower bound**
   on separability, not an estimate (exp003, issue 3.5).
3. The **measured earthquake overlap travels with every call**: 17.2% of real
   earthquakes meet both thresholds on the 120 s segment (exp005), and that overlap is
   magnitude-dependent (~1 in 25 against magnitude-matched events, exp003), because the
   features correlate with size. A classification that hid this would oversell.

The call is a boolean; turning it into P(mass movement) for fusion is done in
``ghadi.fusion.channel_from_seismic`` against assumed operating points, exactly as the
hydro side does — the number's provenance is stated, never hidden.

Features are computed elsewhere (``ghadi.features`` over the decision segment); this
module takes the two scalars so it stays a pure decision rule with no signal-processing
dependency, mirroring how ``ghadi.hydro`` takes a plain array pair.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import DEFAULT, ClassifyConfig


@dataclass(frozen=True)
class SeismicClassification:
    """A mass-movement call over the decision-segment spectral features."""

    mass_movement_like: bool
    segment_lf_hf: float
    segment_centroid_hz: float
    lf_hf_threshold: float
    centroid_threshold_hz: float
    earthquake_overlap: float  # measured false-positive context at this operating point
    reason: str


def classify_segment(
    segment_lf_hf: float,
    segment_centroid_hz: float,
    config: ClassifyConfig | None = None,
) -> SeismicClassification:
    """Apply the decision rule to one window's decision-segment spectral features.

    A feature that is NaN (the signal-presence gate returned no measurement) fails the
    rule: absence of a measurable low-frequency extended source is not evidence of one.
    """
    cfg = config or DEFAULT.classify
    lf_ok = math.isfinite(segment_lf_hf) and segment_lf_hf >= cfg.cascade_segment_lf_hf
    centroid_ok = (
        math.isfinite(segment_centroid_hz)
        and segment_centroid_hz <= cfg.cascade_segment_centroid_hz
    )
    like = lf_ok and centroid_ok

    if like:
        reason = (
            f"LF/HF {segment_lf_hf:.2f} >= {cfg.cascade_segment_lf_hf:.2f} and centroid "
            f"{segment_centroid_hz:.2f} <= {cfg.cascade_segment_centroid_hz:.2f} Hz; "
            f"{cfg.earthquake_overlap * 100:.1f}% of real earthquakes also meet both "
            f"(magnitude-dependent); a lower bound fitted to n=1, not a probability"
        )
    else:
        failed = []
        if not lf_ok:
            failed.append(f"LF/HF {segment_lf_hf:.2f} < {cfg.cascade_segment_lf_hf:.2f}")
        if not centroid_ok:
            failed.append(
                f"centroid {segment_centroid_hz:.2f} > {cfg.cascade_segment_centroid_hz:.2f} Hz"
            )
        reason = "not mass-movement-like: " + "; ".join(failed)

    return SeismicClassification(
        mass_movement_like=like,
        segment_lf_hf=segment_lf_hf,
        segment_centroid_hz=segment_centroid_hz,
        lf_hf_threshold=cfg.cascade_segment_lf_hf,
        centroid_threshold_hz=cfg.cascade_segment_centroid_hz,
        earthquake_overlap=cfg.earthquake_overlap,
        reason=reason,
    )
