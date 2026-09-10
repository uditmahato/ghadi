"""Satellite change detection: confirm and find mass-movement events after the fact.

ANALYSIS PATH ONLY (docs/ARCHITECTURE.md). Nothing here is on the warning path, and it
never can be: free satellites revisit a spot every few days and the Himalaya sits under
monsoon cloud for weeks, so no orbit can see a slope fail and tell a village in minutes.
What imagery can do is answer two different questions, well:

1. **Confirm.** Compare a scene from before an event with one from after. A fresh scar,
   a debris dam, or a breach shows up as a patch of changed ground. That is how a
   seismic detection is proven real after the fact.
2. **Find.** Apply the same comparison around the coarse time and place of a candidate
   historical event. A confirmed patch turns a news report into a labelled positive,
   which is the only way the positive class grows beyond n=1 (issue #6).

**What it can and cannot say.** Imagery gives the WHERE (a changed patch) and bounds the
WHEN (between the two acquisition dates). It never gives the minute; the seismic onset
does. Radar (Sentinel-1) is used first because it sees through cloud; optical
(Sentinel-2) needs a clear view and is usually blocked in monsoon, and this module says
so rather than reporting "no change" for a scene that was really "no view".

This is the pure computation: co-registered arrays in, a :class:`ChangeResult` out, in
numpy and scipy only. Fetching, projection, and caching live in ``ghadi.eo_fetch``, which
imports its raster and catalogue libraries lazily so this module stays cheap to import.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from .config import DEFAULT, EoConfig


@dataclass(frozen=True)
class ChangeResult:
    """Outcome of one before/after comparison over a region of interest."""

    kind: str  # "sar" or "optical"
    verdict: str  # "change_detected" | "no_change" | "inconclusive"
    changed_fraction: float  # changed pixels as a fraction of USABLE pixels
    changed_area_km2: float
    valid_fraction: float  # usable pixels as a fraction of the whole region
    n_blobs: int  # connected changed patches
    largest_blob_km2: float
    largest_blob_centroid_rc: tuple[float, float] | None  # (row, col); caller maps to lat/lon
    decrease_fraction: float  # radar: backscatter fell; optical: vegetation lost
    increase_fraction: float  # radar: backscatter rose; optical: vegetation gained
    reason: str


def sar_log_ratio_db(before: np.ndarray, after: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Backscatter change in decibels, ``10 log10(after / before)``, on linear power."""
    b = np.maximum(np.asarray(before, dtype=float), eps)
    a = np.maximum(np.asarray(after, dtype=float), eps)
    return 10.0 * np.log10(a / b)


def ndvi(red: np.ndarray, nir: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Normalised difference vegetation index from red and near-infrared reflectance."""
    r = np.asarray(red, dtype=float)
    n = np.asarray(nir, dtype=float)
    return (n - r) / np.maximum(n + r, eps)


def _check_shapes(before: np.ndarray, after: np.ndarray) -> None:
    if before.shape != after.shape:
        raise ValueError(
            f"before and after must be co-registered arrays of equal shape; got "
            f"{before.shape} and {after.shape}"
        )
    if before.ndim != 2:
        raise ValueError("expected 2-D single-band arrays")


def _blobs(mask: np.ndarray) -> tuple[int, np.ndarray, tuple[float, float] | None]:
    labels, n = ndimage.label(mask)
    if n == 0:
        return 0, np.zeros(0), None
    sizes = np.asarray(ndimage.sum(mask, labels, index=list(range(1, n + 1))), dtype=float)
    k = int(np.argmax(sizes))
    r, c = ndimage.center_of_mass(mask, labels, k + 1)
    return int(n), sizes, (float(r), float(c))


def _finish(
    kind: str,
    change: np.ndarray,
    decrease: np.ndarray,
    increase: np.ndarray,
    valid: np.ndarray,
    pixel_area_m2: float,
    cfg: EoConfig,
) -> ChangeResult:
    n_total = int(valid.size)
    n_valid = int(valid.sum())
    valid_fraction = n_valid / n_total if n_total else 0.0
    denom = max(n_valid, 1)

    changed = change & valid
    changed_fraction = float(changed.sum()) / denom
    changed_area_km2 = float(changed.sum()) * pixel_area_m2 / 1e6
    n_blobs, sizes, centroid = _blobs(changed)
    largest_km2 = float(sizes.max()) * pixel_area_m2 / 1e6 if n_blobs else 0.0
    dec_fraction = float((decrease & valid).sum()) / denom
    inc_fraction = float((increase & valid).sum()) / denom

    if valid_fraction < cfg.min_valid_fraction:
        # The honest verdict. Cloud, shadow, or missing data hid the ground; a scene
        # nobody could see must never be reported as a scene where nothing happened.
        verdict = "inconclusive"
        reason = (
            f"only {valid_fraction:.0%} of the region is usable, below the "
            f"{cfg.min_valid_fraction:.0%} floor; absence of usable pixels is not absence "
            f"of change"
        )
    elif largest_km2 >= cfg.min_blob_km2:
        verdict = "change_detected"
        reason = (
            f"largest connected changed patch {largest_km2:.3f} km2 (floor "
            f"{cfg.min_blob_km2:g} km2); {changed_fraction:.1%} of usable pixels changed "
            f"({dec_fraction:.1%} decrease, {inc_fraction:.1%} increase)"
        )
    else:
        verdict = "no_change"
        reason = (
            f"largest connected changed patch {largest_km2:.3f} km2 is below the "
            f"{cfg.min_blob_km2:g} km2 floor with {valid_fraction:.0%} of the region usable"
        )

    return ChangeResult(
        kind=kind,
        verdict=verdict,
        changed_fraction=changed_fraction,
        changed_area_km2=changed_area_km2,
        valid_fraction=valid_fraction,
        n_blobs=n_blobs,
        largest_blob_km2=largest_km2,
        largest_blob_centroid_rc=centroid,
        decrease_fraction=dec_fraction,
        increase_fraction=inc_fraction,
        reason=reason,
    )


def detect_change_sar(
    before_linear: np.ndarray,
    after_linear: np.ndarray,
    pixel_area_m2: float,
    valid_mask: np.ndarray | None = None,
    config: EoConfig | None = None,
) -> ChangeResult:
    """Radar change between two same-track scenes of linear-power backscatter.

    The two scenes must share the same relative orbit and look geometry; comparing
    different tracks manufactures change from viewing angle alone. That pairing is the
    fetch layer's job and is asserted there, not here. A median filter tames speckle
    before thresholding, so a single noisy pixel cannot become a "patch".
    """
    cfg = config or DEFAULT.eo
    b = np.asarray(before_linear, dtype=float)
    a = np.asarray(after_linear, dtype=float)
    _check_shapes(b, a)

    finite = np.isfinite(b) & np.isfinite(a) & (b > 0) & (a > 0)
    valid = finite if valid_mask is None else (finite & np.asarray(valid_mask, dtype=bool))

    ratio = sar_log_ratio_db(b, a)
    ratio = np.where(valid, ratio, 0.0)  # neutralise unusable pixels before filtering
    if cfg.speckle_filter_px > 1:
        ratio = ndimage.median_filter(ratio, size=cfg.speckle_filter_px)

    decrease = ratio <= -cfg.sar_change_db
    increase = ratio >= cfg.sar_change_db
    return _finish("sar", decrease | increase, decrease, increase, valid, pixel_area_m2, cfg)


def detect_change_optical(
    ndvi_before: np.ndarray,
    ndvi_after: np.ndarray,
    pixel_area_m2: float,
    valid_mask: np.ndarray | None = None,
    config: EoConfig | None = None,
) -> ChangeResult:
    """Vegetation change between two optical scenes, from NDVI before and after.

    ``valid_mask`` should exclude cloud, cloud shadow, and snow (from the scene
    classification layer). Without it, cloud reads as vegetation loss.
    """
    cfg = config or DEFAULT.eo
    b = np.asarray(ndvi_before, dtype=float)
    a = np.asarray(ndvi_after, dtype=float)
    _check_shapes(b, a)

    finite = np.isfinite(b) & np.isfinite(a)
    valid = finite if valid_mask is None else (finite & np.asarray(valid_mask, dtype=bool))

    drop = np.where(valid, b - a, 0.0)  # positive where vegetation was lost
    loss = drop >= cfg.ndvi_drop
    gain = drop <= -cfg.ndvi_drop
    return _finish("optical", loss | gain, loss, gain, valid, pixel_area_m2, cfg)
