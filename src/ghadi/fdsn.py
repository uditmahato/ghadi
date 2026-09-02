"""Cached waveform access over FDSN.

Contracts (HANDOFF §5.1, §6.1):

- Provider is ``EARTHSCOPE`` — ObsPy's ``Client("IRIS")`` is deprecated.
- ``SY.*`` networks are synthetics and are refused at this layer, so no caller can
  accidentally train on synthetic waveforms.
- Every fetch goes through a content-addressed MiniSEED cache under ``data/cache``,
  keyed by NSLC + window. A second run is offline and byte-identical: the raw server
  response is written to disk once and read from disk thereafter.
- ``GHADI_OFFLINE=1`` forbids network access entirely; a cache miss is then a failure
  *record*, not an exception.
- Batch fetches return per-request failure records and never raise because one
  station is down.

ObsPy is imported lazily: this module sits on the analysis side of the fence and the
detection path never imports it (see docs/ARCHITECTURE.md rule 1).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import SYNTHETIC_NETWORKS, is_offline

PROVIDER = "EARTHSCOPE"


def is_synthetic(network: str) -> bool:
    """True for FDSN synthetic networks (``SY.*``) that must never enter a corpus."""
    return network.upper() in SYNTHETIC_NETWORKS


@dataclass(frozen=True)
class WaveformRequest:
    network: str
    station: str
    location: str
    channel: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        for name, value in (("start", self.start), ("end", self.end)):
            if value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware (HANDOFF §5.3)")
        if self.end <= self.start:
            raise ValueError("end must be after start")

    @property
    def nslc(self) -> str:
        return f"{self.network}.{self.station}.{self.location}.{self.channel}"

    def cache_key(self) -> str:
        start = self.start.astimezone(UTC).isoformat(timespec="seconds")
        end = self.end.astimezone(UTC).isoformat(timespec="seconds")
        return hashlib.sha256(f"{self.nslc}|{start}|{end}".encode()).hexdigest()


@dataclass
class FetchResult:
    request: WaveformRequest
    stream: Any | None  # obspy.Stream when ok, else None
    cache_hit: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.stream is not None


def default_cache_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "cache"


class CachedWaveformClient:
    """FDSN dataselect access with a write-once, content-addressed MiniSEED cache."""

    def __init__(self, cache_dir: Path | None = None, provider: str = PROVIDER) -> None:
        self.cache_dir = cache_dir or default_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        self._client: Any | None = None

    def cache_path(self, request: WaveformRequest) -> Path:
        return self.cache_dir / f"{request.cache_key()}.mseed"

    def _fdsn_client(self) -> Any:
        if self._client is None:
            from obspy.clients.fdsn import Client

            self._client = Client(self.provider)
        return self._client

    def get_waveforms(self, request: WaveformRequest) -> FetchResult:
        """Fetch one request. Returns a failure record instead of raising."""
        if is_synthetic(request.network):
            return FetchResult(
                request,
                None,
                cache_hit=False,
                error=f"network {request.network!r} is synthetic (SY.*) and excluded",
            )

        path = self.cache_path(request)
        if path.exists():
            return self._read_cached(request, path)

        if is_offline():
            return FetchResult(
                request,
                None,
                cache_hit=False,
                error=(
                    f"offline mode ({request.nslc}): not in cache and network access is forbidden"
                ),
            )

        return self._fetch_and_cache(request, path)

    def get_many(self, requests: list[WaveformRequest]) -> list[FetchResult]:
        """Fetch a batch. One station being down never fails the batch."""
        return [self.get_waveforms(r) for r in requests]

    def get_inventory(self, network: str, station: str) -> Any | None:
        """Fetch and cache StationXML (response level) for one station.

        Returns None on failure rather than raising, for the same reason waveform
        fetches return failure records: metadata being unavailable must degrade the
        pipeline, not stop it.
        """
        if is_synthetic(network):
            return None

        path = self.cache_dir / f"stationxml_{network}_{station}.xml"
        if path.exists():
            try:
                from obspy import read_inventory

                return read_inventory(str(path))
            except Exception:
                path.unlink(missing_ok=True)  # corrupt cache entry: refetch below

        if is_offline():
            return None

        try:
            from obspy import read_inventory

            tmp = path.with_suffix(".part")
            self._fdsn_client().get_stations(
                network=network, station=station, level="response", filename=str(tmp)
            )
            tmp.replace(path)
            return read_inventory(str(path))
        except Exception:
            return None

    def to_velocity(
        self,
        stream: Any,
        inventory: Any,
        pre_filt: tuple[float, float, float, float] = (0.05, 0.1, 20.0, 25.0),
    ) -> Any | None:
        """Issue 2.4. Deconvolve the instrument response, returning ground velocity.

        Without this, features are in raw counts and are comparable only within a
        single station — which caps the project at one-station operation and makes
        any cross-station threshold meaningless. Ground velocity in m/s is comparable
        across NK.KKN, IO.EVN and the strong-motion stations alike.

        Returns None on failure; the caller then keeps counts and says so.
        """
        try:
            out = stream.copy()
            out.remove_response(inventory=inventory, output="VEL", pre_filt=pre_filt)
            return out
        except Exception:
            return None

    def _read_cached(self, request: WaveformRequest, path: Path) -> FetchResult:
        try:
            from obspy import read

            return FetchResult(request, read(str(path)), cache_hit=True)
        except Exception as exc:  # corrupt cache entry: report, do not crash the batch
            return FetchResult(
                request, None, cache_hit=True, error=f"cache read failed for {path.name}: {exc}"
            )

    def _fetch_and_cache(self, request: WaveformRequest, path: Path) -> FetchResult:
        try:
            from obspy import UTCDateTime, read

            client = self._fdsn_client()
            tmp = path.with_suffix(".part")
            # filename= saves the raw server response, keeping the cache byte-stable.
            client.get_waveforms(
                network=request.network,
                station=request.station,
                location=request.location or "--",
                channel=request.channel,
                starttime=UTCDateTime(request.start),
                endtime=UTCDateTime(request.end),
                filename=str(tmp),
            )
            tmp.replace(path)
            return FetchResult(request, read(str(path)), cache_hit=False)
        except Exception as exc:
            return FetchResult(request, None, cache_hit=False, error=f"{type(exc).__name__}: {exc}")
