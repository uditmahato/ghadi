"""The live source must survive a station that sends nothing, and say so."""

from __future__ import annotations

import queue
import threading
import time
from datetime import UTC, datetime

import numpy as np
import pytest

from ghadi.sources import SeedLinkSource
from ghadi.stream import Packet


class SilentSource(SeedLinkSource):
    """A server that accepts the connection and never sends a packet."""

    def _connect_and_stream(self, inbox: queue.Queue[Packet | None]) -> None:
        return


class OnePacketSource(SeedLinkSource):
    def _connect_and_stream(self, inbox: queue.Queue[Packet | None]) -> None:
        self.packets_received += 1
        now = datetime.now(tz=UTC)
        inbox.put(Packet(self.station_key, now, 50.0, np.zeros(10), now))


def test_a_silent_station_is_counted_and_backed_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GHADI_OFFLINE", raising=False)
    source = SilentSource(max_backoff_s=0.05)
    got: list[Packet] = []
    thread = threading.Thread(target=lambda: got.extend(source.packets()), daemon=True)
    thread.start()
    time.sleep(0.6)
    source.stop()
    thread.join(timeout=2)
    assert got == []
    assert source.silent_sessions >= 2
    assert source.reconnections == source.silent_sessions
    assert not thread.is_alive(), "stop must end a source that is waiting to reconnect"


def test_a_session_that_delivers_is_not_counted_as_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GHADI_OFFLINE", raising=False)
    source = OnePacketSource(max_backoff_s=0.05)
    first = next(iter(source.packets()))
    source.stop()
    assert first.station == source.station_key
    assert source.silent_sessions == 0
