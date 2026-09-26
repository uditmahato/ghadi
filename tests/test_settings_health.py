"""Issue #34: settings come from a file and cannot loosen safety; health answers."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from ghadi.health import HealthServer
from ghadi.settings import DEFAULT_SETTINGS_TOML, load_settings, parse_settings


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
