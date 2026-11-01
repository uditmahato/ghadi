"""Issue #34: settings come from a file and cannot loosen safety; health answers."""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ghadi.health import (
    MAX_CONSECUTIVE_SILENT_SESSIONS,
    NO_PACKET_GRACE_S,
    HealthServer,
    feed_problems,
)
from ghadi.settings import DEFAULT_SETTINGS_TOML, load_settings, parse_settings
from ghadi.sources import SeedLinkSource
from ghadi.stream import Packet


class UnresolvableSource(SeedLinkSource):
    """A server name that no longer exists: every connection fails before it starts."""

    def _connect_and_stream(self, inbox: queue.Queue[Packet | None]) -> None:
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")


def test_defaults_parse_and_point_at_a_known_station() -> None:
    s = load_settings()
    assert s.station_key == "NK.KKN"
    assert s.reach == "TRISHULI-R07"
    assert s.audit_path.name == "audit.jsonl"
    assert s.hop_s <= s.window_s


def test_a_file_is_read_and_relative_paths_resolve_next_to_it(tmp_path: Path) -> None:
    p = tmp_path / "ghadi.toml"
    p.write_text(DEFAULT_SETTINGS_TOML.replace('state_dir = "data/shadow"', 'state_dir = "state"'))
    s = load_settings(p)
    assert s.state_dir == (tmp_path / "state").resolve()
    assert s.source_path == p


def test_an_unknown_station_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown station"):
        parse_settings('[station]\nkey = "XX.YYY"\n')


def test_a_hop_longer_than_the_window_is_refused() -> None:
    with pytest.raises(ValueError, match="hop_s"):
        parse_settings("[feed]\nwindow_s = 240.0\nhop_s = 300.0\n")


@pytest.mark.parametrize("table", ["alert", "cap", "delivery", "public"])
def test_safety_tables_cannot_appear_in_settings(table: str) -> None:
    with pytest.raises(ValueError, match="not configurable"):
        parse_settings(f'[{table}]\nstatus = "Actual"\n')


def test_health_endpoint_reports_the_snapshot_and_status_code() -> None:
    state = {"ok": True, "windows": 3}
    server = HealthServer(0, lambda: dict(state))
    server.start()
    try:
        with urllib.request.urlopen(server.url, timeout=5) as r:
            assert r.status == 200
            assert json.loads(r.read())["windows"] == 3
        state["ok"] = False
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(server.url, timeout=5)
        assert exc.value.code == 503
    finally:
        server.stop()


def test_health_endpoint_can_be_disabled() -> None:
    disabled = HealthServer(0, lambda: {"ok": True}, enabled=False)
    disabled.start()
    assert not disabled.running
    disabled.stop()


START = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)


def test_a_feed_that_never_delivered_is_not_ok_after_the_grace_period() -> None:
    # The 2026-10-30 deployment: five minutes up, nothing received.
    early = feed_problems(
        now=START + timedelta(seconds=NO_PACKET_GRACE_S - 1),
        started_utc=START,
        last_packet_utc=None,
        consecutive_silent_sessions=0,
    )
    assert early == []
    late = feed_problems(
        now=START + timedelta(minutes=5),
        started_utc=START,
        last_packet_utc=None,
        consecutive_silent_sessions=0,
    )
    assert len(late) == 1
    assert "no packets" in late[0] and "since the service started" in late[0]


def test_a_feed_that_stopped_is_not_ok_after_the_grace_period() -> None:
    last = START + timedelta(hours=2)
    assert not feed_problems(
        now=last + timedelta(seconds=30),
        started_utc=START,
        last_packet_utc=last,
        consecutive_silent_sessions=0,
    )
    stopped = feed_problems(
        now=last + timedelta(seconds=NO_PACKET_GRACE_S + 60),
        started_utc=START,
        last_packet_utc=last,
        consecutive_silent_sessions=0,
    )
    assert len(stopped) == 1
    assert f"for {NO_PACKET_GRACE_S + 60:.0f} s" in stopped[0]


def test_silent_sessions_in_a_row_past_the_limit_are_not_ok() -> None:
    def problems(silent: int) -> list[str]:
        return feed_problems(
            now=START + timedelta(seconds=20),
            started_utc=START,
            last_packet_utc=None,
            consecutive_silent_sessions=silent,
        )

    assert problems(MAX_CONSECUTIVE_SILENT_SESSIONS) == []
    over = problems(MAX_CONSECUTIVE_SILENT_SESSIONS + 1)
    assert len(over) == 1
    assert "in a row delivered nothing" in over[0] and "server name" in over[0]


def test_a_source_that_never_connects_reports_both_problems(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GHADI_OFFLINE", raising=False)
    source = UnresolvableSource(max_backoff_s=0.01)
    thread = threading.Thread(target=lambda: list(source.packets()), daemon=True)
    started = datetime.now(tz=UTC)
    thread.start()
    deadline = time.monotonic() + 5.0
    while source.consecutive_silent_sessions <= 10 and time.monotonic() < deadline:
        time.sleep(0.01)
    source.stop()
    thread.join(timeout=2)
    assert source.packets_received == 0
    assert source.last_primary_packet_utc is None
    found = feed_problems(
        now=started + timedelta(minutes=5),
        started_utc=started,
        last_packet_utc=source.last_primary_packet_utc,
        consecutive_silent_sessions=source.consecutive_silent_sessions,
    )
    assert len(found) == 2
