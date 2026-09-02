"""Nepal Standard Time is UTC+05:45 — an unusual offset that will be got wrong at
least once. HANDOFF §5.3 requires a test; this is it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ghadi.config import DEFAULT, NPT


def test_npt_offset_is_five_hours_forty_five_minutes() -> None:
    assert NPT.utcoffset(None) == timedelta(hours=5, minutes=45)


def test_the_2026_onset_converts_to_the_published_local_time() -> None:
    # Experiment 001 Finding 3: source initiation ~02:52:10 UTC = 08:37:10 NPT.
    utc = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)
    npt = utc.astimezone(NPT)
    assert (npt.hour, npt.minute, npt.second) == (8, 37, 10)


def test_npt_round_trips_through_utc() -> None:
    npt_time = datetime(2026, 8, 26, 8, 37, 10, tzinfo=NPT)
    assert npt_time.astimezone(UTC).astimezone(NPT) == npt_time


def test_hydro_threshold_sits_below_the_observed_trishuli_rate() -> None:
    # Trishuli rose ~9 m in 30 min = 0.30 m/min sustained. The default threshold must
    # sit below that or the reference event itself would not have fired it.
    assert DEFAULT.hydro.rate_threshold_m_per_min < 9.0 / 30.0


def test_cap_defaults_are_not_live() -> None:
    assert DEFAULT.cap.default_status != "Actual"
    assert DEFAULT.cap.default_scope != "Public"
