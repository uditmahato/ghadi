"""Turn a live packet feed into fixed analysis windows (issue #30).

A real time feed does not arrive as tidy windows. Packets come in bursts, out of
order, late, with gaps, and sometimes stop. This module is the only place that deals
with that mess, so the detector and the service keep working on whole windows exactly
as they do offline.

Three rules, each with a reason:

* **A window is never re-emitted.** Once a window has been handed on, a packet that
  belongs to it is counted as late and dropped. A decision that has already been made
  cannot be quietly revised, because it may already have reached a person.
* **Gaps are measured, not hidden.** Missing samples are filled with zeros so the
  detector can run, and ``gap_fraction`` says how much of the window was invented.
  Callers decide what is too much; this layer does not silently pass a mostly empty
  window off as data.
* **Delay is measured per window.** ``max_delay_s`` is the worst gap between a sample's
  time and the moment its packet arrived. It is the number the seven day latency run
  (issue #8) exists to establish, and the live loop reports it for every window.

Windows are aligned to the epoch, so the same wall clock second always
falls in the same window whoever assembles it.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

import numpy as np

__all__ = [
    "Packet",
    "PacketSource",
    "StreamAssembler",
    "StreamWindow",
    "WindowAssembler",
]


@dataclass(frozen=True)
class Packet:
    """One block of samples for one channel, as a feed delivers it."""

    station: str  # "NET.STA", the key the rest of the system uses
    start_utc: datetime
    sampling_rate: float
    data: np.ndarray
    received_utc: datetime

    def __post_init__(self) -> None:
        if self.start_utc.tzinfo is None or self.received_utc.tzinfo is None:
            raise ValueError("packet times must be timezone aware")
        if self.sampling_rate <= 0:
            raise ValueError(f"sampling rate must be positive, got {self.sampling_rate}")

    @property
    def n_samples(self) -> int:
        return int(np.asarray(self.data).size)

    @property
    def end_utc(self) -> datetime:
        return self.start_utc + timedelta(seconds=self.n_samples / self.sampling_rate)

    @property
    def delay_s(self) -> float:
        """Seconds between the last sample's time and the packet arriving."""
        return (self.received_utc - self.end_utc).total_seconds()


class PacketSource(Protocol):
    """Anything that yields packets: a live feed, a replayed file, a test fake."""

    def packets(self) -> Iterator[Packet]: ...


@dataclass(frozen=True)
class StreamWindow:
    """One complete analysis window, with an honest account of how complete it is."""

    station: str
    start_utc: datetime
    end_utc: datetime
    sampling_rate: float
    data: np.ndarray
    gap_fraction: float  # share of samples no packet supplied, filled with zeros
    n_packets: int
    max_delay_s: float  # worst packet delay that contributed to this window

    @property
    def usable_fraction(self) -> float:
        return 1.0 - self.gap_fraction


@dataclass
class _Pending:
    data: np.ndarray
    n_packets: int = 0
    max_delay_s: float = float("-inf")


@dataclass
class WindowAssembler:
    """Assembles one station's packets into overlapping analysis windows.

    Windows are ``window_s`` long and start every ``hop_s`` seconds, aligned to the
    epoch. With ``hop_s == window_s`` they tumble; with a shorter hop they overlap. The
    overlap is not a luxury: the detector discards the first long average length of
    every window while its baseline settles (exp001), so an arrival in the first minute
    of a tumbling window is not seen until the next one. Overlap puts every arrival
    well inside some window.

    Args:
        station: the key packets must carry.
        window_s: window length in seconds.
        sampling_rate: the expected rate. A packet at any other rate is rejected, not
            resampled: a rate change means the channel changed, and quietly stretching
            samples would corrupt every feature downstream.
        hop_s: seconds between window starts. Defaults to ``window_s``.
        grace_s: how long after a window ends to keep waiting for its packets.
    """

    station: str
    window_s: float
    sampling_rate: float
    hop_s: float | None = None
    grace_s: float = 5.0
    _pending: dict[int, _Pending] = field(default_factory=dict, init=False, repr=False)
    _emitted: set[int] = field(default_factory=set, init=False, repr=False)
    rejected_packets: int = field(default=0, init=False)
    late_packets: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.window_s <= 0:
            raise ValueError("window_s must be positive")
        if self.hop_s is None:
            self.hop_s = self.window_s
        if self.hop_s <= 0 or self.hop_s > self.window_s:
            raise ValueError("hop_s must be positive and no longer than window_s")
        for name, seconds in (("window_s", self.window_s), ("hop_s", self.hop_s)):
            samples = seconds * self.sampling_rate
            if abs(samples - round(samples)) > 1e-9:
                raise ValueError(
                    f"{name} {seconds} at {self.sampling_rate} Hz is not a whole number of samples"
                )

    @property
    def hop(self) -> float:
        assert self.hop_s is not None
        return self.hop_s

    @property
    def samples_per_window(self) -> int:
        return round(self.window_s * self.sampling_rate)

    def _window_start(self, index: int) -> datetime:
        return datetime.fromtimestamp(index * self.hop, tz=UTC)

    def _window_end_s(self, index: int) -> float:
        return index * self.hop + self.window_s

    def push(self, packet: Packet) -> list[StreamWindow]:
        """Add a packet. Returns any windows this packet completed."""
        if packet.station != self.station:
            self.rejected_packets += 1
            return []
        if abs(packet.sampling_rate - self.sampling_rate) > 1e-9:
            self.rejected_packets += 1
            return []

        data = np.asarray(packet.data, dtype=float)
        if data.size == 0:
            return []

        times = packet.start_utc.timestamp() + np.arange(data.size) / self.sampling_rate
        # Every window whose span touches this packet.
        first = math.floor((times[0] - self.window_s) / self.hop) + 1
        last = math.floor(times[-1] / self.hop)
        late = False
        touched: list[int] = []
        for index in range(first, last + 1):
            if index in self._emitted:
                late = True
                continue
            start_s = index * self.hop
            slot_of = np.rint((times - start_s) * self.sampling_rate).astype(np.int64)
            mask = (slot_of >= 0) & (slot_of < self.samples_per_window)
            if not bool(mask.any()):
                continue
            pending = self._pending.get(index)
            if pending is None:
                pending = _Pending(np.full(self.samples_per_window, np.nan))
                self._pending[index] = pending
            pending.data[slot_of[mask]] = data[mask]
            pending.n_packets += 1
            pending.max_delay_s = max(pending.max_delay_s, packet.delay_s)
            touched.append(index)
        if late:
            # One late packet is one late delivery, however many samples it carried.
            self.late_packets += 1
        if not touched:
            return []

        # A window is complete once a sample past its end has arrived.
        newest_sample_s = float(times[-1])
        done = sorted(k for k in self._pending if self._window_end_s(k) <= newest_sample_s)
        return [self._emit(i) for i in done]

    def flush(self, now_utc: datetime) -> list[StreamWindow]:
        """Emit every window whose end plus the grace period is in the past.

        This is what covers a feed that goes quiet: without it, the last window before
        an outage would sit in the buffer forever and the outage would look like
        silence rather than a gap.
        """
        cutoff = now_utc.timestamp() - self.grace_s
        done = sorted(k for k in self._pending if self._window_end_s(k) <= cutoff)
        return [self._emit(i) for i in done]

    def _emit(self, index: int) -> StreamWindow:
        pending = self._pending.pop(index)
        self._emitted.add(index)
        # Forget emitted indices far behind the newest one; the set must not grow forever.
        floor_index = index - 4 * math.ceil(self.window_s / self.hop) - 8
        self._emitted = {i for i in self._emitted if i >= floor_index}
        missing = int(np.count_nonzero(np.isnan(pending.data)))
        data = np.nan_to_num(pending.data, nan=0.0)
        start = self._window_start(index)
        return StreamWindow(
            station=self.station,
            start_utc=start,
            end_utc=start + timedelta(seconds=self.window_s),
            sampling_rate=self.sampling_rate,
            data=data,
            gap_fraction=missing / self.samples_per_window,
            n_packets=pending.n_packets,
            max_delay_s=pending.max_delay_s if pending.n_packets else float("nan"),
        )


@dataclass
class StreamAssembler:
    """One assembler per station, so several stations can share a feed."""

    window_s: float
    sampling_rate: float
    hop_s: float | None = None
    grace_s: float = 5.0
    _by_station: dict[str, WindowAssembler] = field(default_factory=dict, init=False, repr=False)

    def _for(self, station: str) -> WindowAssembler:
        assembler = self._by_station.get(station)
        if assembler is None:
            assembler = WindowAssembler(
                station=station,
                window_s=self.window_s,
                sampling_rate=self.sampling_rate,
                hop_s=self.hop_s,
                grace_s=self.grace_s,
            )
            self._by_station[station] = assembler
        return assembler

    def push(self, packet: Packet) -> list[StreamWindow]:
        return self._for(packet.station).push(packet)

    def flush(self, now_utc: datetime) -> list[StreamWindow]:
        out: list[StreamWindow] = []
        for assembler in self._by_station.values():
            out.extend(assembler.flush(now_utc))
        return sorted(out, key=lambda w: (w.start_utc, w.station))

    @property
    def stations(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_station))

    @property
    def late_packets(self) -> int:
        return sum(a.late_packets for a in self._by_station.values())

    @property
    def rejected_packets(self) -> int:
        return sum(a.rejected_packets for a in self._by_station.values())
