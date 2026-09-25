"""Issue #30: the live loop must decide on real windows and refuse to send anything."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from ghadi.config import DEFAULT
from ghadi.live import FeedStats, LiveConfig, observation_from_window, run_shadow
from ghadi.service import AuditLog, HealthMonitor, verify_chain
from ghadi.sources import ReplaySource, packets_from_trace
from ghadi.stream import StreamWindow

SR = 50.0
WINDOW_S = DEFAULT.seismic.window_s
T0 = datetime(2026, 8, 26, 2, 48, 0, tzinfo=UTC)
LIVE = LiveConfig(station="NK.KKN", sampling_rate=SR, window_s=WINDOW_S, hop_s=60.0)


def burst_trace(seconds: float = 600.0, onset_s: float = 300.0, seed: int = 3) -> np.ndarray:
    """Quiet background with one long low frequency arrival, like a slope failure."""
    rng = np.random.default_rng(seed)
    n = round(seconds * SR)
    t = np.arange(n) / SR
    data = rng.normal(0.0, 1.0, n)
    body = (t >= onset_s) & (t < onset_s + 90.0)
    ramp = np.clip((t[body] - onset_s) / 12.0, 0.0, 1.0)
    data[body] += 60.0 * ramp * np.sin(2 * np.pi * 1.4 * t[body])
    return data


def window_from(data: np.ndarray, gap_fraction: float = 0.0) -> StreamWindow:
    return StreamWindow(
        station="NK.KKN",
        start_utc=T0,
        end_utc=T0 + timedelta(seconds=data.size / SR),
        sampling_rate=SR,
        data=data,
        gap_fraction=gap_fraction,
        n_packets=24,
        max_delay_s=4.0,
    )


def test_a_window_with_an_arrival_becomes_an_observation() -> None:
    data = burst_trace(seconds=WINDOW_S, onset_s=90.0)
    verdict = observation_from_window(
        window_from(data), live=LIVE, feed_time=T0 + timedelta(minutes=5)
    )
    assert verdict.reason == "ok"
    assert verdict.observation is not None
    assert verdict.observation.detected_utc > T0
    assert np.isfinite(verdict.observation.segment_lf_hf)


def test_a_quiet_window_produces_no_observation_and_says_why() -> None:
    rng = np.random.default_rng(11)
    quiet = rng.normal(0.0, 1.0, round(WINDOW_S * SR))
    verdict = observation_from_window(
        window_from(quiet), live=LIVE, feed_time=T0 + timedelta(minutes=5)
    )
    assert verdict.reason == "no_trigger"
    assert verdict.observation is None


def test_a_window_that_is_mostly_gap_is_refused_not_decided() -> None:
    data = burst_trace(seconds=WINDOW_S, onset_s=90.0)
    verdict = observation_from_window(
        window_from(data, gap_fraction=0.9), live=LIVE, feed_time=T0 + timedelta(minutes=5)
    )
    assert verdict.reason == "unusable"
    assert verdict.observation is None


def test_a_stale_window_is_still_decided_but_flagged() -> None:
    data = burst_trace(seconds=WINDOW_S, onset_s=90.0)
    verdict = observation_from_window(
        window_from(data), live=LIVE, feed_time=T0 + timedelta(hours=2)
    )
    assert verdict.stale is True
    assert verdict.observation is not None, "a late window is still evidence, just late"


def test_replayed_packets_drive_the_whole_pipeline(tmp_path) -> None:  # type: ignore[no-untyped-def]
    data = burst_trace(seconds=2 * WINDOW_S, onset_s=300.0)
    packets = packets_from_trace(data, SR, T0, station="NK.KKN", packet_s=10.0, delay_s=6.0)
    stats = FeedStats()
    log = AuditLog(tmp_path / "audit.jsonl")
    health = HealthMonitor()

    outcomes = run_shadow(
        ReplaySource(packets),
        reach="TRISHULI-R07",
        model_version="test",
        live=LIVE,
        stats=stats,
        audit_log=log,
        health=health,
    )

    assert stats.windows >= 2
    assert stats.as_dict()["delay_p95_s"] == pytest.approx(6.0, abs=1.0)
    assert outcomes, "the arrival should have produced at least one decision"
    assert health.windows_seen == len(outcomes)
    assert verify_chain(tmp_path / "audit.jsonl"), "the live path must keep the audit chain"


def test_the_live_loop_refuses_to_leave_shadow_mode() -> None:
    with pytest.raises(ValueError, match="shadow only"):
        run_shadow(
            ReplaySource([]),
            reach="TRISHULI-R07",
            model_version="test",
            shadow=False,
        )


def test_feed_statistics_report_the_delay_distribution() -> None:
    stats = FeedStats()
    for delay in (1.0, 2.0, 30.0):
        stats.observe(
            replace(window_from(np.zeros(10)), max_delay_s=delay), usable=True, triggered=False
        )
    assert stats.windows == 3
    assert stats.percentile(50) == pytest.approx(2.0)
