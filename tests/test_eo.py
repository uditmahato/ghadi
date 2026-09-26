"""Satellite change detection on synthetic scenes, including the honesty rule: a scene
nobody could see is "inconclusive", never "no change"."""

from __future__ import annotations

import numpy as np
import pytest

from ghadi.config import DEFAULT, EoConfig
from ghadi.eo import detect_change_optical, detect_change_sar, ndvi, sar_log_ratio_db

PIXEL_AREA = 100.0  # 10 m pixels
SHAPE = (200, 200)  # 2 km x 2 km region


def _scene(value: float = 0.1, seed: int = 0, noise: float = 0.15) -> np.ndarray:
    """Linear-power backscatter with mild multiplicative noise."""
    rng = np.random.default_rng(seed)
    return value * np.exp(rng.normal(0.0, noise, size=SHAPE))


def _with_patch(scene: np.ndarray, factor: float, r0: int = 80, c0: int = 90, size: int = 30):
    out = scene.copy()
    out[r0 : r0 + size, c0 : c0 + size] *= factor
    return out


def test_identical_scenes_show_no_change() -> None:
    before = _scene(seed=1)
    result = detect_change_sar(before, before, PIXEL_AREA)
    assert result.verdict == "no_change"
    assert result.changed_fraction == pytest.approx(0.0)
    assert result.valid_fraction == pytest.approx(1.0)


def test_noise_alone_does_not_become_a_patch() -> None:
    # Independent speckle on the two dates, no real change: the median filter and the
    # blob floor must keep this from reading as a landslide scar.
    before, after = _scene(seed=2), _scene(seed=3)
    result = detect_change_sar(before, after, PIXEL_AREA)
    assert result.verdict == "no_change"
    assert result.largest_blob_km2 < DEFAULT.eo.min_blob_km2


def test_darkened_patch_is_detected_with_area_and_location() -> None:
    before = _scene(seed=4)
    after = _with_patch(before, factor=0.1)  # 10 dB drop over a 300 m square
    result = detect_change_sar(before, after, PIXEL_AREA)
    assert result.verdict == "change_detected"
    assert result.decrease_fraction > result.increase_fraction
    # 30x30 pixels at 100 m2 each = 0.09 km2; allow the filter to nibble the edges.
    assert result.largest_blob_km2 == pytest.approx(0.09, abs=0.015)
    assert result.largest_blob_centroid_rc is not None
    r, c = result.largest_blob_centroid_rc
    assert r == pytest.approx(80 + 14.5, abs=2.0)
    assert c == pytest.approx(90 + 14.5, abs=2.0)


def test_brightened_patch_reports_increase() -> None:
    before = _scene(seed=5)
    after = _with_patch(before, factor=8.0)  # ~9 dB rise: rough fresh deposit
    result = detect_change_sar(before, after, PIXEL_AREA)
    assert result.verdict == "change_detected"
    assert result.increase_fraction > result.decrease_fraction


def test_hidden_ground_is_inconclusive_not_quiet() -> None:
    # A real change is present, but a mask hides 60% of the region (cloud, shadow, or
    # missing data). Reporting "no change" here would be the dishonest answer.
    before = _scene(seed=6)
    after = _with_patch(before, factor=0.1)
    valid = np.zeros(SHAPE, dtype=bool)
    valid[:80, :] = True  # only the top 40% is usable, and it excludes the patch
    result = detect_change_sar(before, after, PIXEL_AREA, valid_mask=valid)
    assert result.verdict == "inconclusive"
    assert result.valid_fraction == pytest.approx(0.4)
    assert "absence of usable pixels" in result.reason


def test_valid_fraction_floor_is_configurable() -> None:
    before = _scene(seed=7)
    after = _with_patch(before, factor=0.1)
    valid = np.zeros(SHAPE, dtype=bool)
    valid[:150, :] = True  # 75% usable, and it includes the patch
    strict = EoConfig(min_valid_fraction=0.90)
    lenient = EoConfig(min_valid_fraction=0.50)
    assert detect_change_sar(before, after, PIXEL_AREA, valid, strict).verdict == "inconclusive"
    assert detect_change_sar(before, after, PIXEL_AREA, valid, lenient).verdict == "change_detected"


def test_optical_vegetation_loss_is_detected() -> None:
    green = np.full(SHAPE, 0.7)
    after = green.copy()
    after[50:90, 60:100] = 0.1  # vegetation stripped to bare ground
    result = detect_change_optical(green, after, PIXEL_AREA)
    assert result.verdict == "change_detected"
    assert result.decrease_fraction > 0
    assert result.largest_blob_km2 == pytest.approx(0.16, abs=0.01)


def test_optical_under_cloud_is_inconclusive() -> None:
    green = np.full(SHAPE, 0.7)
    after = green.copy()
    after[50:90, 60:100] = 0.1
    clear = np.zeros(SHAPE, dtype=bool)
    clear[:60, :] = True  # 30% clear sky
    result = detect_change_optical(green, after, PIXEL_AREA, valid_mask=clear)
    assert result.verdict == "inconclusive"


def test_shape_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="co-registered"):
        detect_change_sar(np.ones((10, 10)), np.ones((12, 10)), PIXEL_AREA)


def test_log_ratio_and_ndvi_helpers() -> None:
    assert sar_log_ratio_db(np.array([1.0]), np.array([10.0]))[0] == pytest.approx(10.0)
    assert sar_log_ratio_db(np.array([1.0]), np.array([0.5]))[0] == pytest.approx(-3.0103, abs=1e-3)
    assert ndvi(np.array([0.1]), np.array([0.5]))[0] == pytest.approx(0.6667, abs=1e-3)


def test_config_exposes_eo() -> None:
    assert isinstance(DEFAULT.eo, EoConfig)
    assert DEFAULT.eo.pixel_size_m == 10.0
