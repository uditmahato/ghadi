"""Issue #30: the live feed layer must be honest about gaps, delay, and late data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from ghadi.stream import Packet, StreamAssembler, WindowAssembler

SR = 50.0
WINDOW_S = 4.0
T0 = datetime(2026, 8, 26, 2, 0, 0, tzinfo=UTC)  # a whole multiple of 4 s


def packet(start: datetime, n: int, delay_s: float = 1.0, value: float = 1.0) -> Packet:
    return Packet(
        station="NK.KKN",
        start_utc=start,
        sampling_rate=SR,
        data=np.full(n, value),
        received_utc=start + timedelta(seconds=n / SR + delay_s),
    )


def assembler() -> WindowAssembler:
    return WindowAssembler(station="NK.KKN", window_s=WINDOW_S, sampling_rate=SR)


def test_contiguous_packets_build_whole_windows() -> None:
    a = assembler()
    out = []
    for i in range(5):  # five 2 s packets: two whole windows plus a part
        out += a.push(packet(T0 + timedelta(seconds=2 * i), 100))
    assert [w.start_utc for w in out] == [T0, T0 + timedelta(seconds=WINDOW_S)]
    assert all(w.gap_fraction == 0.0 for w in out)
    assert all(w.data.size == int(WINDOW_S * SR) for w in out)
    assert out[0].n_packets == 2


def test_a_gap_is_measured_not_hidden() -> None:
    a = assembler()
    a.push(packet(T0, 100))  # first half of window 0
    out = a.push(packet(T0 + timedelta(seconds=4), 100))  # jumps to window 1
    assert len(out) == 1
    assert out[0].gap_fraction == pytest.approx(0.5)
    assert out[0].usable_fraction == pytest.approx(0.5)
    assert not np.isnan(out[0].data).any(), "gaps are zero filled so the detector can run"


def test_a_quiet_feed_flushes_instead_of_holding_the_window_forever() -> None:
    a = assembler()
    a.push(packet(T0, 100))
    assert a.flush(T0 + timedelta(seconds=5)) == [], "still inside the grace period"
    out = a.flush(T0 + timedelta(seconds=30))
    assert [w.start_utc for w in out] == [T0]
    assert out[0].gap_fraction == pytest.approx(0.5)


def test_a_window_is_never_re_emitted() -> None:
    a = assembler()
    a.push(packet(T0, 200))
    first = a.push(packet(T0 + timedelta(seconds=4), 200))
    assert len(first) == 1
    again = a.push(packet(T0, 200))  # the same data arrives late
    assert again == []
    assert a.late_packets == 1


def test_out_of_order_packets_inside_an_open_window_are_kept() -> None:
    a = assembler()
    a.push(packet(T0 + timedelta(seconds=2), 100, value=2.0))  # second half first
    a.push(packet(T0, 100, value=1.0))
    out = a.flush(T0 + timedelta(seconds=30))
    assert len(out) == 1
    assert out[0].gap_fraction == 0.0
    assert out[0].data[0] == 1.0 and out[0].data[-1] == 2.0


def test_delay_reported_is_the_worst_one_in_the_window() -> None:
    a = assembler()
    a.push(packet(T0, 100, delay_s=1.0))
    a.push(packet(T0 + timedelta(seconds=2), 100, delay_s=9.0))
    out = a.flush(T0 + timedelta(seconds=30))
    assert out[0].max_delay_s == pytest.approx(9.0)


def test_a_different_sampling_rate_is_rejected_not_resampled() -> None:
    a = assembler()
    odd = Packet("NK.KKN", T0, 100.0, np.ones(100), T0 + timedelta(seconds=2))
    assert a.push(odd) == []
    assert a.rejected_packets == 1


def test_another_station_is_rejected() -> None:
    a = assembler()
    other = Packet("IO.EVN", T0, SR, np.ones(100), T0 + timedelta(seconds=3))
    assert a.push(other) == []
    assert a.rejected_packets == 1


def test_windows_align_to_the_clock_whoever_assembles_them() -> None:
    a = assembler()
    late_start = T0 + timedelta(seconds=1.5)  # feed joined mid window
    out = a.push(packet(late_start, 300))
    out += a.flush(late_start + timedelta(seconds=60))
    assert [w.start_utc for w in out][:2] == [T0, T0 + timedelta(seconds=WINDOW_S)]
    assert out[0].gap_fraction == pytest.approx(1.5 / WINDOW_S, abs=0.01)
    assert out[1].gap_fraction == pytest.approx(0.5 / WINDOW_S, abs=0.01)  # feed ends mid window


def test_two_stations_are_assembled_side_by_side() -> None:
    s = StreamAssembler(window_s=WINDOW_S, sampling_rate=SR)
    s.push(packet(T0, 200))
    s.push(Packet("IO.EVN", T0, SR, np.ones(200), T0 + timedelta(seconds=5)))
    out = s.flush(T0 + timedelta(seconds=60))
    assert [w.station for w in out] == ["IO.EVN", "NK.KKN"]
    assert s.stations == ("IO.EVN", "NK.KKN")
