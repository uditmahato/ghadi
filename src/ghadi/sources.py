"""Where live packets come from (issue #30).

Two sources implement ``ghadi.stream.PacketSource``:

* ``SeedLinkSource`` connects to a real SeedLink server and yields packets as they
  arrive, reconnecting with a growing backoff when the connection drops. It needs the
  network, so it is not covered by the test suite; everything it does beyond the obspy
  call is kept small on purpose.
* ``ReplaySource`` reads packets out of the local waveform cache and hands them over at
  a chosen speed. It is how the live loop is exercised offline, and how a past event
  can be pushed through the real time path to see what would have happened.

The offline discipline holds: ``ReplaySource`` never touches the network, and
``SeedLinkSource`` refuses to connect when ``GHADI_OFFLINE`` is set.
"""

from __future__ import annotations

import os
import queue
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from .config import PRIMARY_STATION, Station
from .stream import Packet

__all__ = ["ReplaySource", "SeedLinkSource", "packets_from_trace"]

DEFAULT_SEEDLINK_SERVER = "rtserve.iris.washington.edu:18000"


def packets_from_trace(
    data: np.ndarray,
    sampling_rate: float,
    start_utc: datetime,
    *,
    station: str,
    packet_s: float = 10.0,
    delay_s: float = 5.0,
) -> list[Packet]:
    """Cut a continuous trace into feed sized packets with a stated arrival delay."""
    per_packet = max(1, round(packet_s * sampling_rate))
    out: list[Packet] = []
    for begin in range(0, np.asarray(data).size, per_packet):
        chunk = np.asarray(data, dtype=float)[begin : begin + per_packet]
        start = start_utc + timedelta(seconds=begin / sampling_rate)
        end = start + timedelta(seconds=chunk.size / sampling_rate)
        out.append(
            Packet(
                station=station,
                start_utc=start,
                sampling_rate=sampling_rate,
                data=chunk,
                received_utc=end + timedelta(seconds=delay_s),
            )
        )
    return out


@dataclass
class ReplaySource:
    """Replay packets that already exist, optionally in something like real time.

    Args:
        packets: the packets to hand over, in the order the feed would deliver them.
        speed: 0 means as fast as possible, the default for tests and experiments. A
            positive value sleeps between packets so the loop sees realistic spacing,
            divided by this factor.
    """

    packets_in: list[Packet]
    speed: float = 0.0

    def packets(self) -> Iterator[Packet]:
        previous: datetime | None = None
        for packet in self.packets_in:
            if self.speed > 0 and previous is not None:
                wait = (packet.received_utc - previous).total_seconds() / self.speed
                if wait > 0:
                    time.sleep(wait)
            previous = packet.received_utc
            yield packet


@dataclass
class SeedLinkSource:
    """A live SeedLink feed, with reconnection.

    The obspy client is callback driven and blocking, so it runs on its own thread and
    hands packets over a queue. Reconnection uses a growing backoff, and every
    reconnection is counted, because a feed that keeps dropping is a fact the operator
    needs and not something to paper over.
    """

    station: Station = PRIMARY_STATION
    server: str = DEFAULT_SEEDLINK_SERVER
    key: str | None = None  # defaults to "NET.STA"
    # Further streams on the same connection, each with the packet key it travels
    # under: a station's horizontals (see ghadi.live.horizontal_key) or a partner station.
    extra_streams: tuple[tuple[Station, str], ...] = ()
    connect_timeout_s: float = 60.0
    max_backoff_s: float = 60.0
    queue_size: int = 1000
    reconnections: int = field(default=0, init=False)
    dropped_packets: int = field(default=0, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)

    @property
    def station_key(self) -> str:
        return self.key or f"{self.station.network}.{self.station.station}"

    def stop(self) -> None:
        """Ask the feed to end after the next packet."""
        self._stop.set()

    def packets(self) -> Iterator[Packet]:
        if os.environ.get("GHADI_OFFLINE"):
            raise RuntimeError(
                "GHADI_OFFLINE is set and SeedLinkSource needs the network. Use "
                "ReplaySource to drive the live loop offline."
            )
        inbox: queue.Queue[Packet | None] = queue.Queue(maxsize=self.queue_size)
        thread = threading.Thread(
            target=self._run_client, args=(inbox,), name="ghadi-seedlink", daemon=True
        )
        thread.start()
        while True:
            item = inbox.get()
            if item is None:
                return
            yield item
            if self._stop.is_set():
                return

    # -- everything below talks to the network -----------------------------------------
    def _run_client(self, inbox: queue.Queue[Packet | None]) -> None:
        backoff = 1.0
        try:
            while not self._stop.is_set():
                try:
                    self._connect_and_stream(inbox)
                    backoff = 1.0  # a clean end is not a failure to back off from
                except Exception:  # any failure at all means reconnect
                    self.reconnections += 1
                    if self._stop.wait(backoff):
                        break
                    backoff = min(backoff * 2, self.max_backoff_s)
        finally:
            inbox.put(None)

    def _connect_and_stream(self, inbox: queue.Queue[Packet | None]) -> None:
        from obspy.clients.seedlink.easyseedlink import EasySeedLinkClient

        source = self
        keys = {
            (self.station.network, self.station.station, self.station.channel): self.station_key
        }
        for station, key in self.extra_streams:
            keys[(station.network, station.station, station.channel)] = key

        class _Client(EasySeedLinkClient):
            def on_data(self, trace: Any) -> None:
                stats = trace.stats
                key = keys.get((stats.network, stats.station, stats.channel))
                if key is None:
                    return
                packet = Packet(
                    station=key,
                    start_utc=stats.starttime.datetime.replace(tzinfo=UTC),
                    sampling_rate=float(stats.sampling_rate),
                    data=np.asarray(trace.data, dtype=float),
                    received_utc=datetime.now(tz=UTC),
                )
                try:
                    inbox.put_nowait(packet)
                except queue.Full:
                    # Never block the feed thread: a slow consumer must not turn into
                    # backpressure on the socket, which would make delay unmeasurable.
                    source.dropped_packets += 1
                if source._stop.is_set():
                    raise KeyboardInterrupt("stop requested")

        client = _Client(self.server, autoconnect=False)
        # obspy defaults this connection timeout to None, which makes connect() raise
        # before it reaches the network.
        client.conn.timeout = self.connect_timeout_s
        client.connect()
        client.select_stream(self.station.network, self.station.station, self.station.channel)
        for station, _key in self.extra_streams:
            client.select_stream(station.network, station.station, station.channel)
        try:
            client.run()
        except KeyboardInterrupt:
            return
