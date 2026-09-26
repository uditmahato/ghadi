"""Ranking an event window against like-for-like null windows, on synthetic scenes."""

from __future__ import annotations

import zlib
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from ghadi.eo_fetch import SENTINEL1_RTC, Bbox, RoiResult, SceneMeta, cycle_windows
from ghadi.eo_null import WindowSet, compare_event_to_nulls, rank_summary

EVENT = datetime(2026, 8, 26, 2, 52, tzinfo=UTC)
SHAPE = (120, 120)
BBOX: Bbox = (85.4, 28.2, 85.6, 28.3)
ORBITS = (19, 85, 121)


class FakeReader:
    """Serves synthetic backscatter; the first pass after EVENT carries a dark patch."""

    def __init__(self, patch_polarisations: tuple[str, ...] = ("vv", "vh")) -> None:
        self.patch_pols = patch_polarisations
        self.fail: set[str] = set()

    def read_roi(self, scene: SceneMeta, asset: str, bbox: Bbox) -> RoiResult:
        if scene.item_id in self.fail:
            return RoiResult(scene, asset, None, None, None, None, False, error="boom")
        seed = zlib.crc32(f"{scene.item_id}|{asset}".encode())  # deterministic
        rng = np.random.default_rng(seed)
        arr = 0.1 * np.exp(rng.normal(0.0, 0.1, SHAPE))
        if scene.when >= EVENT and asset in self.patch_pols:
            arr[40:70, 40:70] *= 0.1
        return RoiResult(
            scene,
            asset,
            arr.astype(np.float32),
            (10.0, 0.0, 0.0, 0.0, -10.0, 0.0),
            32645,
            10.0,
            True,
        )


def _passes() -> list[SceneMeta]:
    out = []
    for i, orbit in enumerate(ORBITS):
        first = datetime(2026, 6, 20, tzinfo=UTC) + timedelta(days=i * 3)
        for k in range(7):
            day = first + timedelta(days=12 * k)
            out.append(
                SceneMeta(
                    f"S1_{day:%Y%m%d}_o{orbit}",
                    SENTINEL1_RTC,
                    day.strftime("%Y-%m-%dT00:10:00Z"),
                    orbit,
                    "descending",
                    None,
                )
            )
    return out


def _sets() -> tuple[WindowSet, list[WindowSet]]:
    per_track = cycle_windows(_passes(), EVENT, max_lag=3, max_gap_days=13, min_gap_days=11)
    by_lag: dict[int, dict[int, object]] = {}
    for (orbit, _), wins in per_track.items():
        for w in wins:
            by_lag.setdefault(w.lag, {})[orbit] = w
    event = WindowSet("lag 0", "event", by_lag[0])  # type: ignore[arg-type]
    nulls = [WindowSet(f"lag {k}", "null", by_lag[k]) for k in sorted(by_lag) if k > 0]  # type: ignore[arg-type]
    return event, nulls


def test_a_real_change_ranks_first_against_clean_nulls_in_both_polarisations() -> None:
    event, nulls = _sets()
    out = compare_event_to_nulls(FakeReader(), BBOX, event, nulls)
    for pol in ("vv", "vh"):
        rec = out["polarisations"][pol]
        assert rec["status"] == "analysed"
        three = next(g for g in rec["groups"] if len(g["tracks"]) == 3)
        sm = three["summary"]
        assert sm["null_windows_at_or_above_event"] == 0
        assert sm["empirical_p"] == sm["p_floor"]
        assert sm["event_largest_km2"] == pytest.approx(0.09, abs=0.02)


def test_the_change_is_not_invented_where_it_is_absent() -> None:
    event, nulls = _sets()
    out = compare_event_to_nulls(FakeReader(patch_polarisations=("vv",)), BBOX, event, nulls)
    vh = next(g for g in out["polarisations"]["vh"]["groups"] if len(g["tracks"]) == 3)
    assert vh["summary"]["event_largest_km2"] < 0.02


def test_a_null_missing_a_track_is_compared_like_with_like() -> None:
    event, nulls = _sets()
    two_track = WindowSet(
        "lag 1 without 19", "null", {o: w for o, w in nulls[0].windows.items() if o != 19}
    )
    out = compare_event_to_nulls(FakeReader(), BBOX, event, [*nulls, two_track], pols=("vv",))
    groups = {tuple(g["tracks"]): g for g in out["polarisations"]["vv"]["groups"]}
    assert set(groups) == {(19, 85, 121), (85, 121)}
    assert groups[(85, 121)]["summary"]["n_null"] == 1
    # The two-track group's event value is recomputed on those two tracks only.
    assert groups[(85, 121)]["event"] == out["polarisations"]["vv"]["event_by_track_set"]["85+121"]


def test_failed_reads_are_reported_and_the_track_drops_out() -> None:
    event, nulls = _sets()
    reader = FakeReader()
    reader.fail.add(event.windows[19].after.item_id)
    out = compare_event_to_nulls(reader, BBOX, event, nulls, pols=("vv",))
    rec = out["polarisations"]["vv"]
    assert rec["failures"] and rec["failures"][0]["error"] == "boom"
    assert rec["event_tracks"] == [85, 121]
    assert all(len(g["tracks"]) == 2 for g in rec["groups"])


def test_polarisation_agreement_is_higher_where_both_see_the_patch() -> None:
    event, nulls = _sets()
    out = compare_event_to_nulls(FakeReader(), BBOX, event, nulls)
    by_label = {(a["label"], tuple(a["tracks"])): a for a in out["polarisation_agreement"]}
    ev = by_label[("lag 0", (19, 85, 121))]
    assert ev["jaccard"] is not None and ev["jaccard"] > 0.5


def test_locate_hook_receives_the_grid() -> None:
    event, nulls = _sets()
    seen = []

    def locate(transform: tuple[float, ...], epsg: int, r: float, c: float) -> dict[str, float]:
        seen.append((transform, epsg))
        return {"row": round(r, 1), "col": round(c, 1)}

    out = compare_event_to_nulls(FakeReader(), BBOX, event, nulls, pols=("vv",), locate=locate)
    three = out["polarisations"]["vv"]["event_by_track_set"]["19+85+121"]
    assert three["row"] == pytest.approx(54.5, abs=1.0)
    assert seen and seen[0][1] == 32645


def test_rank_summary_states_its_floor_and_rejects_empty() -> None:
    sm = rank_summary(0.4, [0.1, 0.5, 0.2])
    assert sm["null_windows_at_or_above_event"] == 1
    assert sm["empirical_p"] == pytest.approx(0.5)
    assert sm["p_floor"] == pytest.approx(0.25)
    with pytest.raises(ValueError):
        rank_summary(0.4, [])


def test_roles_are_checked() -> None:
    event, nulls = _sets()
    with pytest.raises(ValueError, match="event"):
        compare_event_to_nulls(FakeReader(), BBOX, nulls[0], [event])


class FakeSearcher:
    """Twelve-day passes on three tracks, every year, with one year missing entirely."""

    def __init__(self, missing_year: int | None = None) -> None:
        self.missing_year = missing_year
        self.calls: list[tuple[datetime, datetime]] = []

    def search(self, collection, bbox, start, end):  # type: ignore[no-untyped-def]
        self.calls.append((start, end))
        if start.year == self.missing_year or end.year == self.missing_year:
            return [], "no scenes this year"
        out = []
        for i, orbit in enumerate(ORBITS):
            day = start + timedelta(days=i)
            while day <= end:
                out.append(
                    SceneMeta(
                        f"S1_{day:%Y%m%d}_o{orbit}",
                        SENTINEL1_RTC,
                        day.strftime("%Y-%m-%dT00:10:00Z"),
                        orbit,
                        "descending",
                        None,
                    )
                )
                day += timedelta(days=12)
        return out, None


def test_seasonal_sets_put_earlier_years_on_the_same_calendar_date() -> None:
    from ghadi.eo_null import seasonal_window_sets

    fs = FakeSearcher()
    event, nulls, rec = seasonal_window_sets(
        fs, SENTINEL1_RTC, BBOX, EVENT, years_back=2, max_lag=2, min_gap_days=11, max_gap_days=13
    )
    assert event is not None and event.label == "2026 lag 0"
    labels = [n.label for n in nulls]
    assert "2026 lag 1" in labels and "2025 lag 0" in labels and "2024 lag 2" in labels
    assert all(n.role == "null" for n in nulls)
    for n in nulls:
        if n.label.startswith("2025 lag 0"):
            for w in n.windows.values():
                assert w.before.when.year == 2025
                assert w.before.when < datetime(2025, 8, 26, 2, 52, tzinfo=UTC) <= w.after.when
    assert set(rec["years"]) == {"2026", "2025", "2024"}


def test_a_year_without_scenes_is_recorded_not_fatal() -> None:
    from ghadi.eo_null import seasonal_window_sets

    event, nulls, rec = seasonal_window_sets(
        FakeSearcher(missing_year=2025),
        SENTINEL1_RTC,
        BBOX,
        EVENT,
        years_back=2,
        max_lag=1,
        min_gap_days=11,
        max_gap_days=13,
    )
    assert event is not None
    assert rec["years"]["2025"]["error"] == "no scenes this year"
    assert not any(n.label.startswith("2025") for n in nulls)
    assert any(n.label.startswith("2024") for n in nulls)
