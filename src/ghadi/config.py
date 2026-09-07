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
# The source location carries ~8 km uncertainty and the initiation time ~180 s
# (event catalogue schema, HANDOFF §6.3). Both feed the travel-time uncertainty band.
SOURCE_ZONE_UNCERTAINTY_KM = 8.0
SOURCE_ZONE_ORIGIN_UNCERTAINTY_S = 180.0


# --- river reaches and downstream settlements (M4 travel-time tables) ----------------
@dataclass(frozen=True)
class Settlement:
    """A settlement downstream of a source zone, on a river reach.

    ``observed_arrival_min_2026`` is the surge arrival time measured in the single
    26 August 2026 event, in minutes after initiation. It is the *only* calibration
    point that exists (positive class n=1), so it is stored as a first-class datum
    rather than derived from a model that does not exist. Coordinates are approximate
    settlement centroids, adequate for a straight-line reference distance and no more.
    """

    name: str
    lat: float
    lon: float
    observed_arrival_min_2026: float | None = None


@dataclass(frozen=True)
class RiverReach:
    reach_id: str
    river_system: str
    source_lat: float
    source_lon: float
    settlements: tuple[Settlement, ...]


# Lhende Khola -> Bhote Koshi -> Trishuli, the 26 August 2026 corridor. The three
# settlements and their arrival times are the canonical record (RESEARCH_REPORT §14.2,
# travel_time_to_settlements_min: { timure: 4, syabrubesi: 11, bidur: 38 }). Settlement
# coordinates are approximate centroids on the Bhote Koshi/Trishuli; the observed times,
# not the coordinates, are the calibration.
TRISHULI_R07 = RiverReach(
    reach_id="TRISHULI-R07",
    river_system="Lhende Khola -> Bhote Koshi -> Trishuli",
    source_lat=SOURCE_ZONE_LAT,
    source_lon=SOURCE_ZONE_LON,
    settlements=(
        Settlement("Timure", 28.183, 85.378, observed_arrival_min_2026=4.0),
        Settlement("Syabrubesi", 28.162, 85.334, observed_arrival_min_2026=11.0),
        Settlement("Bidur", 27.870, 85.162, observed_arrival_min_2026=38.0),
    ),
)

RIVER_REACHES: dict[str, RiverReach] = {TRISHULI_R07.reach_id: TRISHULI_R07}


# --- seismic processing -------------------------------------------------------------
@dataclass(frozen=True)
class SeismicConfig:
    band_hz: tuple[float, float] = (0.5, 20.0)  # analysis band (Experiment 001)
    sta_s: float = 5.0  # short-term average window
    lta_s: float = 60.0  # long-term average window; the first LTA-length of every
    # analysis window is discarded (settling artefact — HANDOFF §2.2 Finding 5)
    # Edge taper, in SECONDS rather than as a fraction of the window. A fractional
    # taper scales with window length: alpha=0.05 on a 35-minute window tapers 52 s
    # at each end, which suppresses the samples the LTA baseline is built from and
    # manufactures a trigger the moment the STA clears the taper. See exp001.
    taper_s: float = 5.0
    trigger_on: float = 5.0  # STA/LTA ratio to open a trigger
    trigger_off: float = 2.0  # ratio to close it
    window_s: float = 240.0  # canonical analysis window length
    # Frequency split for the low/high spectral energy ratio. Earthquakes centre at
    # ~3-4 Hz on NK.KKN; the 2026 cascade at 1.44 Hz. The split is a tunable, not truth.
    # exp001: the reported ratio changes by ~3x with this value, so any published
    # LF/HF number must state the split that produced it.
    spectral_split_hz: float = 3.0
    # Signal-presence gate (issue 2.3). A window whose peak envelope does not exceed
    # this multiple of its median envelope has no event in it, and duration-based
    # features must return NaN rather than a number that flatters diffuse noise.
    signal_presence_ratio: float = 5.0
    # How far after the onset to look for the peak that emergence is measured against.
    # Unbounded, the search runs to the end of the window, so a small early trigger
    # followed by a larger later arrival yields a huge emergence — exp002 measured
    # 287.9 s for an earthquake whose window held four triggers. A bound also keeps
    # the feature causal: in real time you act on the trigger you have, and cannot
    # know which of the window's triggers will turn out to be the largest.
    emergence_search_s: float = 120.0
    # How much post-onset signal a feature may use. A feature computed over more than
    # this is unavailable when the alert has to fire, so training on it and serving on
    # a segment is train/serve skew with a safety cost (exp005). Sits inside the 180 s
    # end-to-end budget. Not tuned — a sweep belongs with issue 2.6.
    decision_segment_s: float = 120.0


# --- hydrology ----------------------------------------------------------------------
@dataclass(frozen=True)
class HydroConfig:
    # Trishuli 2026: ~9 m in 30 min = ~0.30 m/min sustained, steeper leading edge.
    # The default absolute threshold deliberately sits below that. [HANDOFF §6.2]
    rate_threshold_m_per_min: float = 0.20
    robust_z_threshold: float = 6.0  # on median/MAD of rate-of-rise
    rate_window_s: float = 300.0  # window over which rate-of-rise is estimated
    baseline_window_s: float = 6 * 3600.0  # history used for the robust baseline


# --- travel time / warning budget ---------------------------------------------------
@dataclass(frozen=True)
class TravelConfig:
    # Time from initiation to an issued alert, everything except the water's own travel:
    # seismic wave to station, detection, fusion, CAP emission, dissemination hand-off.
    # It is SUBTRACTED from the surge arrival time to get the lead time actually
    # delivered. The default sits inside the 180 s end-to-end budget (HANDOFF), with a
    # measured detection floor of median ~16 s SeedLink latency (docs/LATENCY.md).
    warning_latency_s: float = 60.0
    # A settlement's arrival time is honestly known only for the calibrated source. If a
    # candidate source sits further than this from the reach's calibrated source, the
    # observed anchors no longer apply and the estimate must be flagged as extrapolation.
    source_match_tolerance_km: float = 15.0
    # Lead time at or above which a settlement-scale evacuation is plausibly actionable.
    # The Bidur precedent — a school of 1,643 evacuated on ~14 minutes' informal notice
    # (HANDOFF §Appendix) — is the only real-world anchor; ~10 min is the report's [H]
    # judgement, not a measured floor. It flags, it does not gate.
    actionable_lead_min: float = 10.0


# --- DHM gauge telemetry ingestion --------------------------------------------------
@dataclass(frozen=True)
class DhmConfig:
    """Cleaning and liveness parameters for real DHM gauge telemetry (Blocker B2).

    The hydro detector takes a clean ``(times_s, stage_m)`` pair; this config governs
    the adapter that produces one from a raw logger export. Every value is a property of
    the data source, not of the physics, and lives here rather than in ``ghadi.dhm``.
    """

    # DHM telemetry is canonically 5-minute. Used only to judge liveness and to warn on
    # sampling far coarser than the rate-of-rise window can resolve — never to resample.
    expected_sample_interval_s: float = 300.0
    # The gauge is declared dead if the newest sample is older than this multiple of the
    # expected interval, relative to the ingestion time. A dead channel is NOT a
    # low-risk channel (exp008, PR #12): liveness is an ingestion-layer fact, and this
    # is where it is established, never guessed from the waveform.
    staleness_factor: float = 3.0
    # Logger sentinels for "no reading". Masked out, never fed to the detector as stage.
    sentinel_values: tuple[float, ...] = (-9999.0, -999.0, 9999.0)
    # Physically implausible stage bounds for a Himalayan river gauge, in metres after
    # unit normalisation. Readings outside are dropped as bad, not clipped.
    min_plausible_stage_m: float = -5.0
    max_plausible_stage_m: float = 100.0


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
    # Operating-point probabilities for a binary hydro detection entering fusion.
    # These are ASSUMED operating points, not a calibration: a rate-of-rise anomaly
    # is a boolean, and turning it into P(mass movement) honestly needs corroborated
    # events to calibrate against, which do not exist yet (positive class is n=1).
    # Stated here so the assumption is visible and replaceable, never buried in code.
    hydro_detected_p: float = 0.80
    hydro_quiet_p: float = 0.05


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
    travel: TravelConfig = field(default_factory=TravelConfig)
    dhm: DhmConfig = field(default_factory=DhmConfig)
    fusion: FusionConfig = field(default_factory=FusionConfig)
    cap: CapConfig = field(default_factory=CapConfig)


DEFAULT = GhadiConfig()
