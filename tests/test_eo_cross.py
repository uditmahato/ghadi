"""Cross-track agreement and grid alignment: change that several independent viewing
geometries see at the same pixels, with its own control, on one common grid."""

from __future__ import annotations

import numpy as np
import pytest

from ghadi.eo import cross_track_excess, detect_change_sar, sar_change_masks
from ghadi.eo_fetch import SENTINEL1_RTC, RoiResult, SceneMeta, align_arrays

PIXEL_AREA = 100.0
SHAPE = (120, 120)


def _mask(*boxes: tuple[int, int, int, int]) -> np.ndarray:
    m = np.zeros(SHAPE, dtype=bool)
    for r0, r1, c0, c1 in boxes:
        m[r0:r1, c0:c1] = True
    return m


def test_masks_primitive_matches_the_detector() -> None:
    rng = np.random.default_rng(3)
    before = 0.1 * np.exp(rng.normal(0, 0.15, SHAPE))
    after = before.copy()
    after[40:70, 40:70] *= 0.1
    change, dec, inc, valid = sar_change_masks(before, after)
    result = detect_change_sar(before, after, PIXEL_AREA)
    assert float(change.sum()) * PIXEL_AREA / 1e6 == pytest.approx(result.changed_area_km2)
    assert dec.sum() > inc.sum()
    assert valid.all()


def test_two_tracks_agreeing_form_the_patch_and_a_lone_track_does_not() -> None:
    valid = np.ones(SHAPE, dtype=bool)
    shared = (30, 60, 30, 60)  # 30x30 = 0.09 km2, seen by both tracks
    only_a = (80, 100, 10, 30)  # 20x20, seen by track A alone
    ev_a, ev_b = _mask(shared, only_a), _mask(shared)
    ctrl = np.zeros(SHAPE, dtype=bool)
    r = cross_track_excess([ev_a, ev_b], [ctrl, ctrl], [valid, valid], PIXEL_AREA)
    assert r.n_tracks == 2
    assert r.largest_patch_km2 == pytest.approx(0.09)
    assert r.area_km2_by_agreement[2] == pytest.approx(0.09)
    assert r.per_track_excess_km2[0] == pytest.approx(0.13)  # shared + lone
    assert r.per_track_excess_km2[1] == pytest.approx(0.09)


def test_change_also_present_in_the_control_is_not_excess() -> None:
    valid = np.ones(SHAPE, dtype=bool)
    box = (30, 60, 30, 60)
    ev = _mask(box)
    r = cross_track_excess([ev, ev], [_mask(box), _mask(box)], [valid, valid], PIXEL_AREA)
    assert r.largest_patch_km2 == 0.0
    assert r.area_km2_by_agreement[2] == 0.0


def test_three_tracks_report_agreement_levels_and_location() -> None:
    valid = np.ones(SHAPE, dtype=bool)
    core = (50, 70, 50, 70)  # 20x20 seen by all three
    ring = (40, 80, 40, 80)  # 40x40 seen by two
    ev = [_mask(ring), _mask(ring), _mask(core)]
    ctrl = [np.zeros(SHAPE, dtype=bool)] * 3
    r = cross_track_excess(ev, ctrl, [valid] * 3, PIXEL_AREA, min_tracks=2)
    assert r.area_km2_by_agreement[3] == pytest.approx(0.04)
    assert r.area_km2_by_agreement[2] == pytest.approx(0.16)
    assert r.largest_patch_centroid_rc is not None
    row, col = r.largest_patch_centroid_rc
    assert row == pytest.approx(59.5, abs=0.6) and col == pytest.approx(59.5, abs=0.6)


def test_mismatched_grids_are_refused() -> None:
    a = np.zeros(SHAPE, dtype=bool)
    b = np.zeros((100, 120), dtype=bool)
    with pytest.raises(ValueError, match="one pixel grid"):
        cross_track_excess([a, b], [a, b], [a, b], PIXEL_AREA)


def _roi(x0: float, top: float, shape: tuple[int, int], fill: float) -> RoiResult:
    scene = SceneMeta(f"s_{x0}_{top}", SENTINEL1_RTC, "2026-08-16T00:00:00Z", 85, "asc", None)
    arr = np.full(shape, fill, dtype=np.float32)
    return RoiResult(scene, "vv", arr, (10.0, 0.0, x0, 0.0, -10.0, top), 32645, 10.0, True)


def test_align_crops_whole_pixel_offsets_to_the_common_grid() -> None:
    base = _roi(1000.0, 5000.0, (50, 60), 1.0)
    shifted = _roi(1020.0, 4990.0, (50, 60), 2.0)  # 2 px east, 1 px south
    base.array[0, 0] = 9.0  # top-left of base, outside the common extent
    arrays, common = align_arrays([base, shifted])
    assert arrays[0].shape == arrays[1].shape == (49, 58)
    assert common == (10.0, 0.0, 1020.0, 0.0, -10.0, 4990.0)
    assert arrays[0][0, 0] == 1.0  # the marker at base[0,0] was cropped away
    assert float(arrays[1].mean()) == 2.0


def test_align_refuses_fractional_offsets_and_other_projections() -> None:
    a = _roi(1000.0, 5000.0, (20, 20), 1.0)
    frac = _roi(1003.0, 5000.0, (20, 20), 1.0)
    with pytest.raises(ValueError, match="fraction of a pixel"):
        align_arrays([a, frac])
    other = _roi(1000.0, 5000.0, (20, 20), 1.0)
    other.epsg = 32644
    with pytest.raises(ValueError, match="projection"):
        align_arrays([a, other])
