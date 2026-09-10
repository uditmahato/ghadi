"""Frames, passes, and controls: the two pairing rules radar change detection lives by.

One satellite pass arrives as several frames sharing a date and track. Pairing two of
them as a control shows almost no change and falsely inflates an event against it; a
frame that only half covers the region reads as missing data. These tests pin the
fixes: one best-covering frame per pass, and controls from the previous cycle only.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ghadi.eo_fetch import (
    SENTINEL1_RTC,
    SceneMeta,
    bbox_overlap_fraction,
    one_per_pass,
    previous_pass,
    same_track_pairs,
)

ROI = (85.45, 28.20, 85.59, 28.31)  # region of interest
EVENT = datetime(2024, 8, 16, 8, 0, tzinfo=UTC)


def _frame(
    day: int,
    orbit: int,
    bbox: tuple[float, float, float, float] | None,
    suffix: str = "a",
    month: int = 8,
    hour: int = 0,
) -> SceneMeta:
    return SceneMeta(
        item_id=f"S1_2024{month:02d}{day:02d}_o{orbit}_{suffix}",
        collection=SENTINEL1_RTC,
        datetime_utc=f"2024-{month:02d}-{day:02d}T{hour:02d}:10:00Z",
        relative_orbit=orbit,
        orbit_state="ascending",
        cloud_cover=None,
        bbox=bbox,
    )


FULL = (85.0, 27.9, 86.0, 28.6)  # covers the whole region
HALF = (85.0, 27.9, 85.52, 28.6)  # covers only the western half
NONE_BOX = (86.5, 27.0, 87.0, 27.5)  # elsewhere entirely


def test_overlap_fraction_is_share_of_target_covered() -> None:
    assert bbox_overlap_fraction(FULL, ROI) == pytest.approx(1.0)
    assert 0.4 < bbox_overlap_fraction(HALF, ROI) < 0.6
    assert bbox_overlap_fraction(NONE_BOX, ROI) == 0.0


def test_one_frame_kept_per_pass_and_it_is_the_best_covering_one() -> None:
    frames = [_frame(7, 85, HALF, "a"), _frame(7, 85, FULL, "b"), _frame(19, 85, FULL, "c")]
    kept = one_per_pass(frames, ROI)
    assert [s.item_id for s in kept] == ["S1_20240807_o85_b", "S1_20240819_o85_c"]


def test_frames_without_footprints_still_collapse_to_one_per_pass() -> None:
    frames = [_frame(7, 85, None, "a"), _frame(7, 85, None, "b")]
    assert len(one_per_pass(frames, ROI)) == 1
    assert len(one_per_pass(frames, None)) == 1


def test_control_never_comes_from_the_same_pass() -> None:
    # Two frames on 7 Aug (same pass) and one on 26 Jul (previous cycle).
    before = _frame(7, 85, FULL, "a")
    scenes = [_frame(7, 85, HALF, "b", hour=1), before, _frame(26, 85, FULL, "p", month=7)]
    ctrl = previous_pass(scenes, before)
    assert ctrl is not None
    assert ctrl.item_id == "S1_20240726_o85_p"
    assert ctrl.when.date() < before.when.date()


def test_control_picks_the_matching_frame_of_the_previous_cycle() -> None:
    before = _frame(7, 85, FULL, "a")
    scenes = [
        before,
        _frame(26, 85, NONE_BOX, "far", month=7),  # same date, wrong footprint
        _frame(26, 85, FULL, "match", month=7),  # same date, matching footprint
    ]
    ctrl = previous_pass(scenes, before)
    assert ctrl is not None and ctrl.item_id == "S1_20240726_o85_match"


def test_no_earlier_cycle_means_no_control() -> None:
    before = _frame(7, 85, FULL, "a")
    assert previous_pass([before, _frame(7, 85, HALF, "b", hour=2)], before) is None
    assert previous_pass([before, _frame(19, 85, FULL, "later")], before) is None


def test_pairing_after_dedupe_yields_one_pair_per_track() -> None:
    frames = [
        _frame(7, 85, HALF, "a"),
        _frame(7, 85, FULL, "b"),  # same pass as 'a'
        _frame(19, 85, FULL, "c"),
        _frame(19, 85, HALF, "d"),  # same pass as 'c'
    ]
    pairs = same_track_pairs(one_per_pass(frames, ROI), EVENT)
    assert len(pairs) == 1
    before, after = pairs[0]
    assert (before.item_id, after.item_id) == ("S1_20240807_o85_b", "S1_20240819_o85_c")


def test_old_cache_records_without_bbox_still_load() -> None:
    legacy = {
        "item_id": "x",
        "collection": SENTINEL1_RTC,
        "datetime_utc": "2024-08-07T00:10:00Z",
        "relative_orbit": 85,
        "orbit_state": "ascending",
        "cloud_cover": None,
    }
    assert SceneMeta(**legacy).bbox is None
