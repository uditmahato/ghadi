"""All tunable parameters in one place.

Nothing elsewhere in the package hard-codes a band edge, a threshold, a cost ratio,
or a CAP identity. If you are about to write a literal somewhere else, it belongs here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta, timezone

# --- time ---------------------------------------------------------------------------
# Nepal Standard Time. The +05:45 offset is unusual and will be got wrong at least
# once; tests/test_config.py exists so it is got wrong exactly zero shipped times.
NPT = timezone(timedelta(hours=5, minutes=45), name="NPT")

# --- environment flags --------------------------------------------------------------
OFFLINE_ENV = "GHADI_OFFLINE"  # "1" => the fdsn layer must never touch the network
AUTHORIZED_BUILD_ENV = "GHADI_AUTHORIZED_BUILD"  # "1" => CAP may emit Actual/Public


def is_offline() -> bool:
    return os.environ.get(OFFLINE_ENV, "0") == "1"


def is_authorized_build() -> bool:
    return os.environ.get(AUTHORIZED_BUILD_ENV, "0") == "1"


# --- stations and geography ---------------------------------------------------------
@dataclass(frozen=True)
class Station:
    network: str
    station: str
    location: str
    channel: str

    @property
    def nslc(self) -> str:
        return f"{self.network}.{self.station}.{self.location}.{self.channel}"


# Primary open broadband station: Kakani, Nepal. 27.800N 85.279E, 2042 m, 50 Hz,
# operating since 2016-05-22. 55.9 km from the 2026 Bhote Koshi source zone.
PRIMARY_STATION = Station("NK", "KKN", "", "BHZ")
PRIMARY_STATION_3C = (
    Station("NK", "KKN", "", "BHZ"),
    Station("NK", "KKN", "", "BHN"),
    Station("NK", "KKN", "", "BHE"),
)

# SY.* networks on FDSN are synthetics and must be excluded from every query.
SYNTHETIC_NETWORKS = frozenset({"SY"})

# 2026-08-26 source zone (inside TAR/China), reference figures from HANDOFF Appendix B.
SOURCE_ZONE_LAT = 28.255
SOURCE_ZONE_LON = 85.520


# --- seismic processing -------------------------------------------------------------
@dataclass(frozen=True)
class SeismicConfig:
    band_hz: tuple[float, float] = (0.5, 20.0)  # analysis band (Experiment 001)
    sta_s: float = 5.0  # short-term average window
    lta_s: float = 60.0  # long-term average window; the first LTA-length of every
    # analysis window is discarded (settling artefact — HANDOFF §2.2 Finding 5)
    trigger_on: float = 5.0  # STA/LTA ratio to open a trigger
    trigger_off: float = 2.0  # ratio to close it
    window_s: float = 240.0  # canonical analysis window length
    # Frequency split for the low/high spectral energy ratio. Earthquakes centre at
    # ~3-4 Hz on NK.KKN; the 2026 cascade at 1.44 Hz. The split is a tunable, not truth.
    spectral_split_hz: float = 3.0


# --- hydrology ----------------------------------------------------------------------
@dataclass(frozen=True)
class HydroConfig:
    # Trishuli 2026: ~9 m in 30 min = ~0.30 m/min sustained, steeper leading edge.
    # The default absolute threshold deliberately sits below that. [HANDOFF §6.2]
    rate_threshold_m_per_min: float = 0.20
    robust_z_threshold: float = 6.0  # on median/MAD of rate-of-rise
    rate_window_s: float = 300.0  # window over which rate-of-rise is estimated
    baseline_window_s: float = 6 * 3600.0  # history used for the robust baseline


# --- fusion -------------------------------------------------------------------------
@dataclass(frozen=True)
class FusionConfig:
    # A missed cascade costs lives; a false alarm costs an evacuation and trust.
    # The ratio is published, not hidden inside a threshold. [report §17.3]
    cost_miss_over_false_alarm: float = 50.0
    watch_p: float = 0.20  # fused probability => WATCH
    advisory_p: float = 0.50  # => ADVISORY
    warning_p: float = 0.80  # => WARNING (also requires >= 2 independent groups alive)
    min_groups_for_warning: int = 2


# --- CAP ----------------------------------------------------------------------------
@dataclass(frozen=True)
class CapConfig:
    sender: str = "ghadi@example.invalid"  # replaced under an operating agreement
    identifier_prefix: str = "GHADI"
    default_status: str = "Test"  # never "Actual" outside an authorised build
    default_scope: str = "Restricted"  # never "Public" outside an authorised build
    default_language_en: str = "en-US"
    default_language_ne: str = "ne-NP"


# --- top level ----------------------------------------------------------------------
@dataclass(frozen=True)
class GhadiConfig:
    seismic: SeismicConfig = field(default_factory=SeismicConfig)
    hydro: HydroConfig = field(default_factory=HydroConfig)
    fusion: FusionConfig = field(default_factory=FusionConfig)
    cap: CapConfig = field(default_factory=CapConfig)


DEFAULT = GhadiConfig()
