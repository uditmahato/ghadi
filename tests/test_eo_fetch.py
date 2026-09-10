"""The satellite fetch layer's pure parts and its offline discipline. No network."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from ghadi.config import OFFLINE_ENV
from ghadi.eo_fetch import (
    SENTINEL1_RTC,
    CachedSceneClient,
    SceneMeta,
    bbox_around,
    roi_cache_key,
    same_track_pairs,
    sentinel2_clear_mask,
    sentinel2_reflectance,
)

EVENT = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)


def _scene(day: int, orbit: int, state: str = "descending", month: int = 8) -> SceneMeta:
    return SceneMeta(
        item_id=f"S1_{month:02d}{day:02d}_o{orbit}",
        collection=SENTINEL1_RTC,
        datetime_utc=f"2026-{month:02d}-{day:02d}T00:10:00Z",
        relative_orbit=orbit,
        orbit_state=state,
        cloud_cover=None,
    )


def test_bbox_is_square_and_centred() -> None:
    w, s, e, n = bbox_around(28.255, 85.520, 5.0)
    assert (w + e) / 2 == pytest.approx(85.520)
    assert (s + n) / 2 == pytest.approx(28.255)
    assert n - s == pytest.approx(10.0 / 111.2, rel=1e-3)
    assert e - w > n - s  # longitude degrees are shorter at 28 N


def test_pairs_are_same_track_and_straddle_the_event() -> None:
    scenes = [
        _scene(19, 121),
        _scene(31, 121),  # orbit 121: 19 Aug -> 31 Aug
        _scene(24, 19),
        _scene(5, 19, month=9),  # orbit 19: 24 Aug -> 5 Sep
        _scene(16, 85, "ascending"),
        _scene(28, 85, "ascending"),  # orbit 85
        _scene(4, 85, "ascending"),  # an earlier 'before' that must not be chosen
    ]
    pairs = same_track_pairs(scenes, EVENT)
    assert len(pairs) == 3
    for before, after in pairs:
        assert before.relative_orbit == after.relative_orbit
        assert before.orbit_state == after.orbit_state
        assert before.when < EVENT <= after.when
    # The latest before and earliest after on each track, shortest gap first.
    assert next((b.item_id, a.item_id) for b, a in pairs) in {
        ("S1_0819_o121", "S1_0831_o121"),
        ("S1_0824_o19", "S1_0905_o19"),
        ("S1_0816_o85", "S1_0828_o85"),
    }
    chosen_85 = next(p for p in pairs if p[0].relative_orbit == 85)
    assert chosen_85[0].item_id == "S1_0816_o85"  # not the 4 Aug scene


def test_different_tracks_are_never_paired() -> None:
    scenes = [_scene(24, 19), _scene(28, 85, "ascending")]
    assert same_track_pairs(scenes, EVENT) == []


def test_missing_side_or_wide_gap_yields_no_pair() -> None:
    assert same_track_pairs([_scene(19, 121), _scene(24, 121)], EVENT) == []  # no after
    wide = [_scene(1, 121, month=7), _scene(9, 121, month=9)]  # 70-day gap
    assert same_track_pairs(wide, EVENT, max_gap_days=30) == []


def test_naive_event_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        same_track_pairs([], datetime(2026, 8, 26))


def test_sentinel2_helpers() -> None:
    scl = np.array([[4, 8, 9], [3, 6, 11]])
    assert sentinel2_clear_mask(scl).tolist() == [[True, False, False], [False, True, False]]
    assert sentinel2_reflectance(np.array([1000, 3000]))[0] == pytest.approx(0.0)
    assert sentinel2_reflectance(np.array([1000, 3000]))[1] == pytest.approx(0.2)


def test_roi_cache_key_is_stable_and_specific() -> None:
    bbox = (85.4, 28.2, 85.6, 28.3)
    k1 = roi_cache_key("item-a", "vv", bbox)
    assert k1 == roi_cache_key("item-a", "vv", bbox)
    assert k1 != roi_cache_key("item-a", "vh", bbox)
    assert k1 != roi_cache_key("item-b", "vv", bbox)


def test_offline_cache_miss_is_a_failure_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(OFFLINE_ENV, "1")
    client = CachedSceneClient(cache_dir=tmp_path)
    scenes, err = client.search(SENTINEL1_RTC, (85.4, 28.2, 85.6, 28.3), EVENT, EVENT)
    assert scenes == [] and err is not None and "offline" in err
    roi = client.read_roi(_scene(28, 85), "vv", (85.4, 28.2, 85.6, 28.3))
    assert not roi.ok and roi.error is not None and "offline" in roi.error
    with pytest.raises(ValueError):
        _ = roi.pixel_area_m2


def test_cached_region_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Write a cache entry by hand, then read it back offline: the read path must not
    # need the network or the raster libraries.
    monkeypatch.setenv(OFFLINE_ENV, "1")
    client = CachedSceneClient(cache_dir=tmp_path)
    scene, bbox = _scene(28, 85), (85.4, 28.2, 85.6, 28.3)
    path = tmp_path / f"roi_{roi_cache_key(scene.item_id, 'vv', bbox)}.npz"
    arr = np.full((4, 5), 0.2, dtype=np.float32)
    np.savez_compressed(
        path,
        array=arr,
        transform=np.array([10.0, 0, 349747.5, 0, -10.0, 3131382.7]),
        epsg=np.array(32645),
        pixel_size_m=np.array(10.0),
    )
    roi = client.read_roi(scene, "vv", bbox)
    assert roi.ok and roi.cache_hit
    assert roi.array is not None and roi.array.shape == (4, 5)
    assert roi.epsg == 32645 and roi.pixel_area_m2 == pytest.approx(100.0)


def test_fetch_layer_imports_raster_libraries_lazily() -> None:
    """Importing ghadi.eo_fetch must not drag in rasterio or the STAC client."""
    probe = (
        "import ghadi.eo_fetch, ghadi.eo, sys; "
        "print(any(m in sys.modules for m in "
        "('rasterio', 'pystac_client', 'planetary_computer')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"
