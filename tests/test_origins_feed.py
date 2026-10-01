"""The rolling catalogue: late, fallible, and never an empty sky by accident."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ghadi.origins_feed import RollingOrigins, fetch_usgs, parse_usgs_csv
from ghadi.teleseism import Origin

NOW = datetime(2026, 9, 26, 16, 45, 0, tzinfo=UTC)
YEMEN = Origin(datetime(2026, 9, 26, 16, 33, 43, tzinfo=UTC), 13.2741, 51.4282, 5.2, "us1", "Yemen")

CSV = (
    "time,latitude,longitude,depth,mag,magType,nst,gap,dmin,rms,net,id,updated,place\n"
    "2026-09-26T16:33:43.000Z,13.2741,51.4282,10,5.2,mb,,,,,us,us1,,148 km NW of Kilmia\n"
    "not a row\n"
    "2026-09-26T15:01:36.000Z,-21.3884,168.5751,10,5.1,mb,,,,,us,us2,,New Caledonia\n"
)


def test_csv_rows_become_origins_and_bad_rows_are_skipped() -> None:
    origins = parse_usgs_csv(CSV)
    assert [o.event_id for o in origins] == ["us1", "us2"]
    assert origins[0].time_utc.tzinfo is not None
    assert origins[0].magnitude == 5.2


def test_refresh_reports_only_what_is_new() -> None:
    served = [[YEMEN], [YEMEN]]
    feed = RollingOrigins(fetch=lambda a, b, m: served.pop(0), refresh_s=60)
    assert feed.refresh(NOW) == [YEMEN]
    assert feed.refresh(NOW + timedelta(seconds=120)) == []
    assert feed.origins == (YEMEN,)


def test_a_fetch_is_not_repeated_before_it_is_due() -> None:
    calls = []
    feed = RollingOrigins(fetch=lambda a, b, m: calls.append(1) or [], refresh_s=120)
    feed.current(NOW)
    feed.current(NOW + timedelta(seconds=30))
    assert len(calls) == 1


def test_a_failed_fetch_keeps_what_was_held_and_says_so() -> None:
    state = {"fail": False}

    def fetch(a: datetime, b: datetime, m: float) -> list[Origin]:
        if state["fail"]:
            raise OSError("network down")
        return [YEMEN]

    feed = RollingOrigins(fetch=fetch, refresh_s=1)
    feed.refresh(NOW)
    state["fail"] = True
    assert feed.refresh(NOW + timedelta(seconds=10)) == []
    assert feed.origins == (YEMEN,), "a failed fetch is not an empty sky"
    assert feed.failures == 1 and "network down" in str(feed.last_error)


def test_old_origins_fall_out_of_the_window() -> None:
    feed = RollingOrigins(fetch=lambda a, b, m: [], refresh_s=1, lookback_s=3600)
    feed.origins = (YEMEN,)
    feed.refresh(NOW + timedelta(hours=3))
    assert feed.origins == ()


def test_the_default_fetcher_refuses_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GHADI_OFFLINE", "1")
    with pytest.raises(RuntimeError, match="GHADI_OFFLINE"):
        fetch_usgs(NOW - timedelta(hours=1), NOW, 4.5)
