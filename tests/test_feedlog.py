"""Issue #8: every window is kept on disk, so the latency run survives a restart."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from ghadi.feedlog import FeedLog, read_feed_log, summarise_feed_log
from ghadi.live import FeedStats, LiveConfig, WindowVerdict, run_shadow
from ghadi.sources import ReplaySource, packets_from_trace
from ghadi.stream import StreamWindow

T0 = datetime(2026, 11, 2, 0, 0, tzinfo=UTC)
KEY = "NK.KKN"


def verdict(
    minute: int,
    *,
    delay: float = 18.0,
    reason: str = "no_trigger",
    stale: bool = False,
    station: str = KEY,
    gap: float = 0.0,
) -> WindowVerdict:
    start = T0 + timedelta(minutes=minute)
    window = StreamWindow(
        station=station,
        start_utc=start,
        end_utc=start + timedelta(seconds=240),
        sampling_rate=50.0,
        data=np.zeros(10),
        gap_fraction=gap,
        n_packets=30,
        max_delay_s=delay,
    )
    return WindowVerdict(window, None, reason, stale)


def write_run(log: FeedLog, minutes: range, **kw: float) -> None:
    log.start(station=KEY, server="test:18000", window_s=240.0, hop_s=60.0)
    for m in minutes:
        log.window(verdict(m, **kw))
    log.stop(feed={"windows": len(minutes)})


def test_windows_from_several_runs_are_summarised_together(tmp_path: Path) -> None:
    log = FeedLog(tmp_path / "windows.jsonl")
    write_run(log, range(0, 60), delay=15.0)
    # A restart: the in memory statistics would start again from zero here.
    write_run(log, range(60, 120), delay=25.0)
    s = summarise_feed_log(log.path, KEY)
    assert s["service_starts"] == 2
    assert s["windows"] == 120
    assert s["hours_watched"] == 2.0
    assert s["delay_p50_s"] == 20.0
    assert s["delay_max_s"] == 25.0
    assert s["interruptions_over_120_s"] == 0


def test_an_outage_is_counted_and_measured(tmp_path: Path) -> None:
    log = FeedLog(tmp_path / "windows.jsonl")
    write_run(log, range(0, 10))
    write_run(log, range(30, 40))
    s = summarise_feed_log(log.path, KEY)
    assert s["interruptions_over_120_s"] == 1
    # Windows start at minute 9 and minute 30: 21 minutes apart, one hop of it normal.
    assert s["longest_interruption_s"] == 20 * 60


def test_backlog_partner_and_upgrades_do_not_count_as_feed_delay(tmp_path: Path) -> None:
    log = FeedLog(tmp_path / "windows.jsonl")
    log.window(verdict(0, delay=20.0))
    log.window(verdict(1, delay=3000.0, stale=True))
    log.window(verdict(2, delay=900.0, station="IO.EVN", reason="partner"))
    log.window(verdict(0, delay=20.0, reason="upgraded"))
    log.window(verdict(3, delay=22.0, reason="unusable", gap=0.7))
    s = summarise_feed_log(log.path, KEY, hop_s=60.0)
    assert s["windows"] == 3
    assert s["stale_windows"] == 1
    assert s["usable_windows"] == 2
    assert s["delay_max_s"] == 22.0
    assert s["reasons"] == {"no_trigger": 2, "unusable": 1}


def test_a_line_cut_short_by_a_crash_is_skipped(tmp_path: Path) -> None:
    log = FeedLog(tmp_path / "windows.jsonl")
    write_run(log, range(0, 3))
    with log.path.open("a", encoding="utf-8") as fh:
        fh.write('{"kind":"window","station":"NK.KK')
    write_run(log, range(3, 5))
    assert len([e for e in read_feed_log(log.path) if e["kind"] == "window"]) == 5
    assert summarise_feed_log(log.path, KEY)["windows"] == 5


def test_since_limits_the_summary(tmp_path: Path) -> None:
    log = FeedLog(tmp_path / "windows.jsonl")
    write_run(log, range(0, 120))
    s = summarise_feed_log(log.path, KEY, since=T0 + timedelta(minutes=60))
    assert s["windows"] == 60
    assert s["first_window_utc"] == (T0 + timedelta(minutes=60)).isoformat()


def test_an_empty_or_missing_log_summarises_to_nothing(tmp_path: Path) -> None:
    s = summarise_feed_log(tmp_path / "absent.jsonl", KEY)
    assert s["windows"] == 0
    assert s["delay_p95_s"] is None


def test_the_log_agrees_with_the_live_loop(tmp_path: Path) -> None:
    rng = np.random.default_rng(5)
    data = rng.normal(0.0, 1.0, round(20 * 60 * 50.0))
    packets = packets_from_trace(data, 50.0, T0, station=KEY, packet_s=10.0, delay_s=6.0)
    log = FeedLog(tmp_path / "windows.jsonl")
    stats = FeedStats()
    run_shadow(
        ReplaySource(packets),
        reach="TRISHULI-R07",
        model_version="test",
        live=LiveConfig(station=KEY, sampling_rate=50.0, window_s=240.0, hop_s=60.0),
        stats=stats,
        on_verdict=log.window,
    )
    s = summarise_feed_log(log.path, KEY, hop_s=60.0)
    assert stats.windows > 10
    assert s["windows"] == stats.windows
    assert s["delay_p95_s"] == round(stats.percentile(95), 2)
