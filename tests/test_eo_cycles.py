"""Consecutive-cycle windows: the event window and its earlier no-event null windows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ghadi.eo_fetch import SENTINEL1_RTC, SceneMeta, cycle_windows

EVENT = datetime(2026, 8, 26, 2, 52, tzinfo=UTC)


def _pass(day: datetime, orbit: int | None, state: str = "descending", tag: str = "") -> SceneMeta:
    return SceneMeta(
        item_id=f"S1_{day:%Y%m%d}_o{orbit}{tag}",
        collection=SENTINEL1_RTC,
        datetime_utc=day.strftime("%Y-%m-%dT00:10:00Z"),
        relative_orbit=orbit,
        orbit_state=state,
        cloud_cover=None,
    )


def _track(orbit: int, first: datetime, n: int, state: str = "descending") -> list[SceneMeta]:
    return [_pass(first + timedelta(days=12 * i), orbit, state) for i in range(n)]


def test_lag_zero_straddles_the_event_and_later_lags_lie_before_it() -> None:
    scenes = _track(19, datetime(2026, 6, 25, tzinfo=UTC), 7)  # 25 Jun .. 5 Sep
    wins = cycle_windows(scenes, EVENT, max_lag=3)[(19, "descending")]
    assert [w.lag for w in wins] == [0, 1, 2, 3]
    assert wins[0].before.when < EVENT <= wins[0].after.when
    for w in wins[1:]:
        assert w.after.when < EVENT
    for w in wins:
        assert w.control_before.when < w.before.when < w.after.when


def test_each_lag_shifts_back_one_cycle() -> None:
    scenes = _track(85, datetime(2026, 6, 20, tzinfo=UTC), 7, "ascending")
    wins = cycle_windows(scenes, EVENT, max_lag=2)[(85, "ascending")]
    assert wins[1].after == wins[0].before
    assert wins[1].before == wins[0].control_before
    assert wins[2].after == wins[1].before


def test_lags_stop_when_history_runs_out() -> None:
    scenes = _track(121, datetime(2026, 8, 7, tzinfo=UTC), 3)  # 7, 19, 31 Aug
    wins = cycle_windows(scenes, EVENT, max_lag=5)[(121, "descending")]
    assert [w.lag for w in wins] == [0]


def test_a_missing_acquisition_stops_the_sequence_rather_than_widening_a_window() -> None:
    scenes = _track(19, datetime(2026, 6, 1, tzinfo=UTC), 9)
    del scenes[4]  # remove 18 Jul, leaving a 24 day gap
    wins = cycle_windows(scenes, EVENT, max_lag=6, max_gap_days=13.0)[(19, "descending")]
    assert all(
        (w.after.when - w.before.when).days <= 13
        and (w.before.when - w.control_before.when).days <= 13
        for w in wins
    )
    assert len(wins) < 7


def test_tracks_are_kept_separate_and_duplicate_frames_collapse() -> None:
    a = _track(19, datetime(2026, 7, 31, tzinfo=UTC), 4)
    b = _track(85, datetime(2026, 8, 4, tzinfo=UTC), 3, "ascending")
    dup = _pass(datetime(2026, 8, 12, tzinfo=UTC), 19, tag="_frame2")  # same pass as a[1]
    out = cycle_windows([*a, *b, dup], EVENT, max_lag=1)
    assert set(out) == {(19, "descending"), (85, "ascending")}
    for track, wins in out.items():
        for w in wins:
            assert {w.before.relative_orbit, w.after.relative_orbit} == {track[0]}
            assert (
                len({w.control_before.when.date(), w.before.when.date(), w.after.when.date()}) == 3
            )


def test_tracks_without_an_after_pass_or_orbit_are_skipped() -> None:
    before_only = _track(19, datetime(2026, 7, 1, tzinfo=UTC), 4)  # ends 6 Aug
    no_orbit = [_pass(datetime(2026, 8, d, tzinfo=UTC), None) for d in (1, 13, 30)]
    assert cycle_windows([*before_only, *no_orbit], EVENT, max_lag=2) == {}


def test_bad_arguments_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        cycle_windows([], datetime(2026, 8, 26), max_lag=1)
    with pytest.raises(ValueError, match="non-negative"):
        cycle_windows([], EVENT, max_lag=-1)


def test_short_windows_from_a_second_satellite_are_skipped_not_stopping() -> None:
    days = [
        "2026-06-01",
        "2026-06-13",
        "2026-06-25",
        "2026-07-02",
        "2026-07-14",
        "2026-07-26",
        "2026-08-07",
        "2026-08-19",
        "2026-08-31",
    ]
    scenes = [_pass(datetime.fromisoformat(d).replace(tzinfo=UTC), 121) for d in days]
    wins = cycle_windows(scenes, EVENT, max_lag=6, min_gap_days=11.0)[(121, "descending")]
    lags = [w.lag for w in wins]
    assert lags == [0, 1, 2, 3, 6]  # lags 4 and 5 include the 7 day gap
    for w in wins:
        assert (w.after.when - w.before.when).days == 12
        assert (w.before.when - w.control_before.when).days == 12
