"""FDSN layer: synthetic exclusion, cache keying, offline mode, graceful failure."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ghadi.config import OFFLINE_ENV
from ghadi.fdsn import PROVIDER, CachedWaveformClient, WaveformRequest, is_synthetic

START = datetime(2026, 8, 26, 2, 43, 30, tzinfo=UTC)
END = START + timedelta(minutes=35)


def _request(network: str = "NK", station: str = "KKN") -> WaveformRequest:
    return WaveformRequest(network, station, "", "BHZ", START, END)


def test_provider_is_earthscope_not_the_deprecated_iris() -> None:
    # ObsPy's Client("IRIS") now emits a deprecation warning (HANDOFF issue 0.3).
    assert PROVIDER == "EARTHSCOPE"


def test_synthetic_networks_are_recognised() -> None:
    assert is_synthetic("SY")
    assert is_synthetic("sy")
    assert not is_synthetic("NK")


def test_synthetic_request_is_refused_without_touching_the_network(tmp_path: Path) -> None:
    client = CachedWaveformClient(cache_dir=tmp_path)
    result = client.get_waveforms(_request(network="SY"))
    assert not result.ok
    assert "synthetic" in (result.error or "")


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        WaveformRequest("NK", "KKN", "", "BHZ", datetime(2026, 8, 26, 2, 43, 30), END)


def test_end_must_follow_start() -> None:
    with pytest.raises(ValueError, match="after start"):
        WaveformRequest("NK", "KKN", "", "BHZ", END, START)


def test_cache_key_is_stable_and_window_sensitive() -> None:
    a = _request()
    b = WaveformRequest("NK", "KKN", "", "BHZ", START, END)
    c = WaveformRequest("NK", "KKN", "", "BHZ", START, END + timedelta(seconds=1))
    assert a.cache_key() == b.cache_key()
    assert a.cache_key() != c.cache_key()
    assert _request(station="EVN").cache_key() != a.cache_key()


def test_offline_mode_reports_a_miss_instead_of_fetching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(OFFLINE_ENV, "1")
    client = CachedWaveformClient(cache_dir=tmp_path)
    result = client.get_waveforms(_request())
    assert not result.ok
    assert "offline" in (result.error or "")


def test_batch_survives_a_dead_station(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # One station being down must never raise and kill the batch (HANDOFF §5.1).
    monkeypatch.setenv(OFFLINE_ENV, "1")
    client = CachedWaveformClient(cache_dir=tmp_path)
    results = client.get_many([_request(), _request(network="SY"), _request(station="EVN")])
    assert len(results) == 3
    assert all(not r.ok for r in results)
    assert all(r.error for r in results)
