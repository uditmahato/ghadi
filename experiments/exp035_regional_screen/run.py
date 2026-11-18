"""Experiment 035: would a lower regional earthquake screen remove the live false alarms?

**Question.** The first fortnight of the live shadow run (2 to 18 November 2026) staged
16 Advisories on NK.KKN, about 31 a month against a goal of 1. Six were distant M5.0 to
M5.2 earthquakes the current screen explains. Of the other ten, six fit regional M4.4 to
M4.9 earthquakes 4 to 16 degrees away, below the screen's M5.0. Would a lower regional
screen, for example M4.4 and above within 20 degrees, remove them, and what does it cost
in time with the seismic channel set aside? Would it ever have hidden the one positive,
the 26 August 2026 Bhote Koshi event?

**Design.** The screen in operation is ``ghadi.config.SuppressionConfig``: M5.5 and above
anywhere, M5.0 and above within 80 degrees. Each setting here keeps that and adds a
regional tier: M ``near_mag`` and above within ``near_deg`` degrees of the station, for
near_mag in 4.0, 4.4, 4.7, 5.0 and near_deg in 10, 15, 20, 30. The same code paths as
operation: ``ghadi.teleseism.magnitude_applies`` decides whether an origin counts,
``phase_window`` gives its window and ``explain`` decides whether a time is explained.

* **Catalogue.** USGS, 2024-01-01 to 2026-11-19: M4.0 and above within 32 degrees of
  NK.KKN, and M5.0 and above everywhere, every event type, as the live parser reads it.
* **Time set aside** over the full year 2025, per station, and over the live fortnight.
* **Noise false alarms** from exp018 (zero margin) and exp022 (the live 20 percent
  margin, with and without H/V). A window is removed only when every passing segment in
  it is explained.
* **The 16 live Advisories**, at the trigger time where it is known and otherwise at the
  staged time less 156 s (exp020's median from onset to decision).
* **The 2026 event** at its onsets (NK.KKN 02:52:30.3, IO.EVN 02:52:43.1, exp019), with
  the catalogue as it is now, with the origin as USGS first published it, and with what
  was published by the decision at 02:55:00 (exp020).
* **Publication time.** For each regional origin from 1 August to 18 November 2026, the
  earliest origin product in the USGS event history, against the decision time at
  NK.KKN and against the live feed's two hour look back.
* **A guarded variant** of every setting: earthquakes only, and nothing within 50 km of
  the reach of the catchment above Bidur (144 km of the 2026 source zone), applied to
  every tier.

The first online run caches the catalogue and the publication history beside this
script; later runs need no network (``GHADI_OFFLINE=1``).

    python experiments/exp035_regional_screen/run.py
"""

from __future__ import annotations

import bisect
import csv
import importlib.util
import io
import json
import math
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.basin import load_basin  # noqa: E402
from ghadi.config import DEFAULT, EVEREST, KAKANI, StationSite  # noqa: E402
from ghadi.geo import haversine_km  # noqa: E402
from ghadi.origins_feed import USGS_ENDPOINT, RollingOrigins  # noqa: E402
from ghadi.teleseism import (  # noqa: E402
    Origin,
    epicentral_distance_deg,
    explain,
    magnitude_applies,
    p_travel_time_s,
    phase_window,
)

HERE = Path(__file__).resolve().parent
EXP018 = REPO_ROOT / "experiments" / "exp018_io_evn_false_alarm_rate" / "results.json"
EXP022 = REPO_ROOT / "experiments" / "exp022_margin_and_joint_rules" / "results.json"
REGIONAL_CACHE = HERE / "catalogue_regional_m40.json"
GLOBAL_CACHE = HERE / "catalogue_global_m50.json"
PUBLICATION_CACHE = HERE / "publication.json"
EMSC_CACHE = HERE / "catalogue_emsc_live.json"
EMSC_ENDPOINT = "https://www.seismicportal.eu/fdsnws/event/1/query"


def _load_exp024() -> Any:
    spec = importlib.util.spec_from_file_location(
        "exp024", REPO_ROOT / "experiments" / "exp024_suppression_threshold" / "run.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXP024 = _load_exp024()
covered_fraction = EXP024.covered_fraction

CATALOGUE = (datetime(2024, 1, 1, tzinfo=UTC), datetime(2026, 11, 19, tzinfo=UTC))
YEAR = (datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC))
LIVE_PERIOD = (datetime(2026, 11, 2, tzinfo=UTC), datetime(2026, 11, 19, tzinfo=UTC))
LATENCY_PERIOD = (datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 11, 19, tzinfo=UTC))
REGIONAL_FETCH_DEG = 32.0
REGIONAL_MIN_MAG = 4.0
SITES: dict[str, StationSite] = {"NK.KKN": KAKANI, "IO.EVN": EVEREST}

NEAR_MAGS = (4.0, 4.4, 4.7, 5.0)
NEAR_DEGS = (10.0, 15.0, 20.0, 30.0)
CURRENT = DEFAULT.suppression

# The guarded variant protects the watched catchment from every tier of the screen: no
# origin within reach of the catchment above Bidur, plus a margin for the error of a
# first published location (the 2026 event's first USGS origin was 33 km from the
# source), may set the channel aside or explain an alert. Measured from exp022's zone
# around the 2026 source.
PROTECT_POINT = (28.255, 85.520)
PROTECT_MARGIN_KM = 50.0
_CATCHMENT = load_basin()
PROTECT_KM = (
    max(
        haversine_km(PROTECT_POINT[0], PROTECT_POINT[1], la, lo)
        for la, lo in zip(_CATCHMENT.lats, _CATCHMENT.lons, strict=True)
    )
    + PROTECT_MARGIN_KM
)

# exp020: the decision on the live path comes about 156 s after the onset (median), and
# from 126 s to 186 s.
DECISION_AFTER_ONSET_S = 156.0
DECISION_RANGE_S = (126.0, 186.0)
LOOKBACK_S = RollingOrigins().lookback_s
FEED_MIN_MAG = RollingOrigins().min_magnitude

EVENT_2026 = {
    "NK.KKN": datetime(2026, 8, 26, 2, 52, 30, 300000, tzinfo=UTC),
    "IO.EVN": datetime(2026, 8, 26, 2, 52, 43, 100000, tzinfo=UTC),
}
EVENT_2026_DECISION = datetime(2026, 8, 26, 2, 55, 0, tzinfo=UTC)
EVENT_2026_HOURS = (
    datetime(2026, 8, 26, 0, 0, tzinfo=UTC),
    datetime(2026, 8, 26, 6, 0, tzinfo=UTC),
)
# A longer look back than the live feed's two hours, to show what it would recover.
LONG_LOOKBACK_S = 7 * 24 * 3600.0
EVENT_2026_USGS_ID = "us7000tbwb"


# The 16 Advisories the live service staged on NK.KKN from 2 to 18 November 2026. Onsets
# as recovered on 2026-11-18 without the shadow machine's state: "archive" recomputed
# from the EarthScope archive (the first trigger before staging whose segment passes
# the rule), "outbox" from the after the fact line (predicted P plus or minus the stated
# offset, the sign that puts staging 126 to 186 s after onset; both signs where both
# fit), and "staged" where only the staged time is known.
def _adv(
    short_id: str,
    staged: str,
    basis: str,
    onsets: tuple[str, ...],
    check: str,
) -> dict[str, Any]:
    return {
        "id": f"GHADI-LIVE-{short_id}",
        "staged_utc": f"2026-11-{staged}+00:00",
        "onset_basis": basis,
        "onsets_utc": [f"2026-11-{o}+00:00" for o in onsets],
        "check_2026_11_18": check,
    }


LIVE_ADVISORIES: list[dict[str, Any]] = [
    _adv(
        "f2dc21c114fb",
        "02T15:40:24",
        "archive",
        ("02T15:37:20.540",),
        "M4.7 us7000tuxi, Xizang-Qinghai border, confirmed in the signal",
    ),
    _adv(
        "9fa4b8c7c1c7",
        "02T21:00:20",
        "archive",
        ("02T20:57:02.460",),
        "M4.5 us7000tuzz, same area, confirmed in the signal",
    ),
    _adv(
        "42846552e395",
        "03T16:59:22",
        "archive",
        ("03T16:56:57.380",),
        "explained live: M5.2 Volcano Islands",
    ),
    _adv(
        "1872091fcf8e",
        "03T20:42:23",
        "archive",
        ("03T20:39:29.740",),
        "unexplained; P then a stronger S 25 s later, likely an uncatalogued local "
        "earthquake about 200 km away",
    ),
    _adv(
        "7ab98bdba682",
        "03T21:43:20",
        "archive",
        ("03T21:40:28.540",),
        "explained live: M5.2 Kyrgyzstan",
    ),
    _adv(
        "0584f9419052",
        "04T20:15:23",
        "archive, approximate",
        ("04T20:12:53.380",),
        "weak teleseismic match; the recomputed trigger narrowly fails the rule",
    ),
    _adv("a0f7dc64d0e1", "08T09:01:26.800", "staged", (), "unexplained"),
    _adv("9acc43bdf571", "08T20:28:22.400", "staged", (), "weak teleseismic match"),
    _adv(
        "014ddc0634dc",
        "09T10:00:34.750",
        "outbox",
        ("09T09:57:33", "09T09:57:49"),
        "explained live: M5.2 Indonesia",
    ),
    _adv(
        "63233343367b",
        "09T10:42:25.290",
        "staged",
        (),
        "catalogue timing only: M4.4 Tajikistan us7000tx3a",
    ),
    _adv(
        "1a91da207b62",
        "14T03:07:16.350",
        "outbox",
        ("14T03:05:00",),
        "explained live: M5.2 Sumatra",
    ),
    _adv(
        "9a5c5f35d62a",
        "14T03:53:27.440",
        "staged",
        (),
        "catalogue timing only: M4.5 central India, EMSC 20261114_0000284",
    ),
    _adv(
        "c4cfb5f4ce70",
        "15T15:57:31.840",
        "outbox",
        ("15T15:54:33",),
        "explained live: M5.1 Gorontalo",
    ),
    _adv(
        "c64d00494256",
        "15T17:54:21.870",
        "outbox",
        ("15T17:51:53",),
        "explained live: M5.0 Afghanistan",
    ),
    _adv(
        "e63638fbf4db",
        "15T21:46:19.340",
        "staged",
        (),
        "catalogue timing only: M4.4 Nepal-India border EMSC 20261115_0000259 "
        "or M4.9 Afghanistan us7000tyga",
    ),
    _adv(
        "0ed3a703d0e9",
        "18T00:56:24.170",
        "staged",
        (),
        "catalogue timing only: M4.7 Tajikistan, EMSC 20261118_0000021",
    ),
]


# --- catalogue ------------------------------------------------------------------------
@dataclass(frozen=True)
class Row:
    """A catalogue row with the fields the screen ignores but this experiment needs."""

    origin: Origin
    event_type: str
    mag_type: str


def _offline_guard() -> None:
    if os.environ.get("GHADI_OFFLINE"):
        raise RuntimeError(
            "GHADI_OFFLINE is set and a cache is missing; run once online to build it"
        )


def _get(url: str) -> str:
    _offline_guard()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return str(response.read().decode("utf-8"))
        except OSError:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def _usgs_rows(params: dict[str, str]) -> list[dict[str, Any]]:
    text = _get(f"{USGS_ENDPOINT}?{urllib.parse.urlencode({'format': 'csv', **params})}")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            out.append(
                {
                    "time_utc": datetime.fromisoformat(
                        r["time"].replace("Z", "+00:00")
                    ).isoformat(),
                    "latitude": float(r["latitude"]),
                    "longitude": float(r["longitude"]),
                    "magnitude": float(r["mag"]),
                    "mag_type": r.get("magType", ""),
                    "event_id": r.get("id", ""),
                    "place": r.get("place", ""),
                    "event_type": r.get("type", ""),
                    "updated_utc": r.get("updated", ""),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _fetch_chunked(extra: dict[str, str], days: int, cache: Path) -> list[dict[str, Any]]:
    if cache.exists():
        rows: list[dict[str, Any]] = json.loads(cache.read_text(encoding="utf-8"))
        return rows
    rows = []
    cursor = CATALOGUE[0]
    while cursor < CATALOGUE[1]:
        stop = min(cursor + timedelta(days=days), CATALOGUE[1])
        rows += _usgs_rows(
            {
                "starttime": cursor.strftime("%Y-%m-%dT%H:%M:%S"),
                "endtime": stop.strftime("%Y-%m-%dT%H:%M:%S"),
                "orderby": "time-asc",
                **extra,
            }
        )
        print(f"   {cache.name}: to {stop.date()}, {len(rows)} origins", flush=True)
        cursor = stop
    cache.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def load_catalogue() -> list[Row]:
    regional = _fetch_chunked(
        {
            "latitude": f"{KAKANI.latitude}",
            "longitude": f"{KAKANI.longitude}",
            "maxradius": f"{REGIONAL_FETCH_DEG:g}",
            "minmagnitude": f"{REGIONAL_MIN_MAG:g}",
        },
        180,
        REGIONAL_CACHE,
    )
    worldwide = _fetch_chunked({"minmagnitude": "5.0"}, 120, GLOBAL_CACHE)
    merged: dict[str, dict[str, Any]] = {}
    for r in regional + worldwide:
        merged[r["event_id"] or f"{r['time_utc']}|{r['latitude']}|{r['longitude']}"] = r
    out = [
        Row(
            Origin(
                datetime.fromisoformat(r["time_utc"]),
                r["latitude"],
                r["longitude"],
                r["magnitude"],
                r["event_id"],
                r["place"],
            ),
            r["event_type"],
            r["mag_type"],
        )
        for r in merged.values()
    ]
    return sorted(out, key=lambda x: x.origin.time_utc)


def load_emsc() -> list[Row]:
    """EMSC origins for the live fortnight and the hours around the 2026 event.

    A side check only: the live feed reads USGS, and the EMSC service gives no first
    publication time, so EMSC enters the tables only where it says so.
    """
    if EMSC_CACHE.exists():
        raw: list[dict[str, Any]] = json.loads(EMSC_CACHE.read_text(encoding="utf-8"))
    else:
        raw = []
        for start, end in (LIVE_PERIOD, EVENT_2026_HOURS):
            params = {
                "format": "json",
                "start": start.strftime("%Y-%m-%dT%H:%M:%S"),
                "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
                "lat": f"{KAKANI.latitude}",
                "lon": f"{KAKANI.longitude}",
                "maxradius": f"{REGIONAL_FETCH_DEG:g}",
                "minmag": f"{REGIONAL_MIN_MAG:g}",
                "limit": "5000",
            }
            data = json.loads(_get(f"{EMSC_ENDPOINT}?{urllib.parse.urlencode(params)}"))
            for f in data.get("features", []):
                p = f["properties"]
                raw.append(
                    {
                        "time_utc": datetime.fromisoformat(
                            p["time"].replace("Z", "+00:00")
                        ).isoformat(),
                        "latitude": float(p["lat"]),
                        "longitude": float(p["lon"]),
                        "magnitude": float(p["mag"]),
                        "mag_type": p.get("magtype", ""),
                        "event_id": f"emsc:{p.get('unid', '')}",
                        "place": p.get("flynn_region", ""),
                        "evtype": p.get("evtype", ""),
                        "last_update_utc": p.get("lastupdate", ""),
                    }
                )
        EMSC_CACHE.write_text(json.dumps(raw, indent=1), encoding="utf-8")
    return [
        Row(
            Origin(
                datetime.fromisoformat(r["time_utc"]),
                r["latitude"],
                r["longitude"],
                r["magnitude"],
                r["event_id"],
                r["place"],
            ),
            # EMSC "ke" is a known earthquake; anything else is not one for the guard.
            "earthquake" if r["evtype"] == "ke" else f"emsc {r['evtype']}",
            r["mag_type"],
        )
        for r in raw
    ]


# --- screens --------------------------------------------------------------------------
@dataclass(frozen=True)
class Screen:
    name: str
    near_mag: float | None  # None: the current screen alone
    near_deg: float
    guarded: bool


def screens() -> list[Screen]:
    out = [Screen("current", None, 0.0, False), Screen("current_guarded", None, 0.0, True)]
    for guarded in (False, True):
        for m in NEAR_MAGS:
            for d in NEAR_DEGS:
                tag = "_guarded" if guarded else ""
                out.append(Screen(f"M{m:.1f}_within_{d:.0f}deg{tag}", m, d, guarded))
    return out


def protected(origin: Origin) -> bool:
    km = haversine_km(PROTECT_POINT[0], PROTECT_POINT[1], origin.latitude, origin.longitude)
    return km <= PROTECT_KM


def eligible(rows: list[Row], screen: Screen) -> list[Origin]:
    """The origins a screen may use at all, before magnitude and distance."""
    if not screen.guarded:
        return [r.origin for r in rows]
    return [r.origin for r in rows if r.event_type == "earthquake" and not protected(r.origin)]


def counts(origin: Origin, site: StationSite, screen: Screen) -> bool:
    """Does this origin set the channel aside under the screen? The live rule, then the tier."""
    deg = epicentral_distance_deg(site.latitude, site.longitude, origin)
    if magnitude_applies(
        origin.magnitude, deg, CURRENT.min_magnitude, CURRENT.near_min_magnitude, CURRENT.near_deg
    ):
        return True
    return screen.near_mag is not None and magnitude_applies(
        origin.magnitude, deg, math.inf, screen.near_mag, screen.near_deg
    )


def recent(origins: list[Origin], when: datetime) -> list[Origin]:
    """Origins from three hours before ``when`` to ten minutes after it.

    No phase window lasts longer than three hours, and none opens more than the lead
    margin (with the diffracted extra) before its origin time.

    Only a speed up; ``explain`` still decides. ``origins`` must be sorted by time.
    """
    held = _TIMES.get(id(origins))
    if held is None or held[0] is not origins:
        # The list is held as well, so its id cannot be reused by another list.
        held = _TIMES[id(origins)] = (origins, [o.time_utc for o in origins])
    times = held[1]
    lo = bisect.bisect_left(times, when - timedelta(hours=3))
    hi = bisect.bisect_right(times, when + timedelta(minutes=10))
    return origins[lo:hi]


_TIMES: dict[int, tuple[list[Origin], list[datetime]]] = {}


def explained_by(
    when: datetime, origins: list[Origin], site: StationSite, screen: Screen
) -> Origin | None:
    """``explain`` under the live rule, then under the regional tier alone."""
    origins = recent(origins, when)
    found = explain(
        when,
        origins,
        site.latitude,
        site.longitude,
        min_magnitude=CURRENT.min_magnitude,
        near_min_magnitude=CURRENT.near_min_magnitude,
        near_deg=CURRENT.near_deg,
    )
    if found.suppressed:
        return found.origin
    if screen.near_mag is None:
        return None
    found = explain(
        when,
        origins,
        site.latitude,
        site.longitude,
        min_magnitude=math.inf,
        near_min_magnitude=screen.near_mag,
        near_deg=screen.near_deg,
    )
    return found.origin if found.suppressed else None


def windows(
    origins: list[Origin], site: StationSite, screen: Screen
) -> list[tuple[datetime, datetime]]:
    out = []
    for o in origins:
        if counts(o, site, screen):
            opens, closes, _ = phase_window(o, site.latitude, site.longitude)
            out.append((opens, closes))
    return sorted(out)


# --- noise false alarms ---------------------------------------------------------------
def noise_windows() -> dict[str, dict[str, list[list[datetime]]]]:
    """Per station and corpus rule: each false alarm window as its passing segment times."""
    exp018 = json.loads(EXP018.read_text(encoding="utf-8"))
    exp022 = json.loads(EXP022.read_text(encoding="utf-8"))
    out: dict[str, dict[str, list[list[datetime]]]] = {}
    for key in SITES:
        rules: dict[str, list[list[datetime]]] = {}
        rules["exp018_spectral_zero_margin"] = [
            [
                datetime.fromisoformat(w["window_start_utc"]) + timedelta(seconds=s["on_s"])
                for s in w["passing_segments"]
            ]
            for w in exp018["stations"][key]["false_alarm_windows"]
        ]
        thr = exp022["stations"][key]["by_margin"]["0.2"]["thresholds"]
        spectral: list[list[datetime]] = []
        spectral_hv: list[list[datetime]] = []
        for w in exp022["stations"][key]["windows"]:
            start = datetime.fromisoformat(w["window_start_utc"])
            s_times, h_times = [], []
            for s in w["segments"]:
                if s["lf_hf"] >= thr["lf_hf_min"] and s["centroid_hz"] <= thr["centroid_hz_max"]:
                    when = start + timedelta(seconds=s["on_s"])
                    s_times.append(when)
                    if s.get("hv_segment") is not None and s["hv_segment"] >= thr["hv_min"]:
                        h_times.append(when)
            if s_times:
                spectral.append(s_times)
            if h_times:
                spectral_hv.append(h_times)
        rules["exp022_spectral_20pct"] = spectral
        rules["exp022_spectral_hv_20pct"] = spectral_hv
        out[key] = rules
    return out


def removed(
    corpus: list[list[datetime]], origins: list[Origin], site: StationSite, screen: Screen
) -> int:
    return sum(1 for segs in corpus if all(explained_by(t, origins, site, screen) for t in segs))


# --- publication time -----------------------------------------------------------------
def publication(rows: list[Row]) -> dict[str, dict[str, Any]]:
    """The first origin product USGS published for each regional origin in the period."""
    cached: dict[str, dict[str, Any]] = (
        json.loads(PUBLICATION_CACHE.read_text(encoding="utf-8"))
        if PUBLICATION_CACHE.exists()
        else {}
    )
    wanted = [
        r
        for r in rows
        if LATENCY_PERIOD[0] <= r.origin.time_utc < LATENCY_PERIOD[1]
        and epicentral_distance_deg(KAKANI.latitude, KAKANI.longitude, r.origin) <= 30.0
        and r.origin.magnitude >= REGIONAL_MIN_MAG
    ]
    # And every M5.0 and above in the live fortnight, so the live screen's own after the
    # fact explanations can be checked against the feed's look back.
    wanted += [
        r
        for r in rows
        if LIVE_PERIOD[0] <= r.origin.time_utc < LIVE_PERIOD[1]
        and r.origin.magnitude >= 5.0
        and r not in wanted
    ]
    ids = [r.origin.event_id for r in wanted]
    if EVENT_2026_USGS_ID not in ids:
        ids.append(EVENT_2026_USGS_ID)
    missing = [i for i in ids if i not in cached]
    for n, event_id in enumerate(missing, 1):
        url = f"{USGS_ENDPOINT}?" + urllib.parse.urlencode(
            {"format": "geojson", "eventid": event_id, "includesuperseded": "true"}
        )
        detail = json.loads(_get(url))
        versions = []
        for product in detail["properties"]["products"].get("origin", []):
            p = product.get("properties", {})
            versions.append(
                {
                    "published_utc": datetime.fromtimestamp(
                        product["updateTime"] / 1000, UTC
                    ).isoformat(),
                    "source": product.get("source", ""),
                    "event_time_utc": p.get("eventtime", ""),
                    "latitude": float(p["latitude"]) if p.get("latitude") else None,
                    "longitude": float(p["longitude"]) if p.get("longitude") else None,
                    "magnitude": float(p["magnitude"]) if p.get("magnitude") else None,
                    "magnitude_type": p.get("magnitude-type", ""),
                    "event_type": p.get("event-type", ""),
                }
            )
        versions.sort(key=lambda v: v["published_utc"])
        cached[event_id] = {"origin_versions": versions}
        if n % 25 == 0 or n == len(missing):
            print(f"   publication history: {n} of {len(missing)}", flush=True)
            PUBLICATION_CACHE.write_text(json.dumps(cached, indent=1), encoding="utf-8")
        time.sleep(0.3)
    if missing:
        PUBLICATION_CACHE.write_text(json.dumps(cached, indent=1), encoding="utf-8")
    return {i: cached[i] for i in ids}


def magnitude_bin(m: float) -> str:
    if m < 4.4:
        return "M4.0 to 4.3"
    if m < 4.7:
        return "M4.4 to 4.6"
    if m < 5.0:
        return "M4.7 to 4.9"
    return "M5.0 and above"


def latency_summary(rows: list[Row], pub: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_id = {r.origin.event_id: r for r in rows}
    per_event = []
    for event_id, rec in pub.items():
        if event_id == EVENT_2026_USGS_ID or event_id not in by_id or not rec["origin_versions"]:
            continue
        o = by_id[event_id].origin
        deg = epicentral_distance_deg(KAKANI.latitude, KAKANI.longitude, o)
        if deg > 30.0 or not LATENCY_PERIOD[0] <= o.time_utc < LATENCY_PERIOD[1]:
            continue
        first = rec["origin_versions"][0]
        published = datetime.fromisoformat(first["published_utc"])
        decision = o.time_utc + timedelta(seconds=p_travel_time_s(deg) + DECISION_AFTER_ONSET_S)
        per_event.append(
            {
                "event_id": event_id,
                "magnitude": o.magnitude,
                "first_magnitude": first["magnitude"],
                "distance_deg": round(deg, 1),
                "delay_min": (published - o.time_utc).total_seconds() / 60.0,
                "before_decision": published <= decision,
                "within_lookback": (published - o.time_utc).total_seconds() <= LOOKBACK_S,
                "within_7d": (published - o.time_utc).total_seconds() <= LONG_LOOKBACK_S,
                "first_at_or_above_feed": (first["magnitude"] or 0.0) >= FEED_MIN_MAG,
            }
        )
    bins: dict[str, Any] = {}
    for name in ("M4.0 to 4.3", "M4.4 to 4.6", "M4.7 to 4.9", "M5.0 and above", "all"):
        sel = [e for e in per_event if name == "all" or magnitude_bin(e["magnitude"]) == name]
        if not sel:
            continue
        delays = sorted(e["delay_min"] for e in sel)
        bins[name] = {
            "origins": len(sel),
            "median_delay_min": round(statistics.median(delays), 1),
            "p90_delay_min": round(delays[min(len(delays) - 1, int(0.9 * len(delays)))], 1),
            "published_before_decision": sum(e["before_decision"] for e in sel),
            "published_within_lookback_2h": sum(e["within_lookback"] for e in sel),
            "published_within_7d": sum(e["within_7d"] for e in sel),
            "first_version_at_or_above_feed_m45": sum(e["first_at_or_above_feed"] for e in sel),
        }
    named = {}
    for event_id in ("us7000tuxi", "us7000tuzz", "us7000tx3a", "us7000tyga"):
        e = next((x for x in per_event if x["event_id"] == event_id), None)
        if e is not None:
            named[event_id] = {
                k: (round(v, 1) if isinstance(v, float) else v) for k, v in e.items()
            }
    return {
        "period": [LATENCY_PERIOD[0].isoformat(), LATENCY_PERIOD[1].isoformat()],
        "within_deg_of_nk_kkn": 30.0,
        "by_magnitude": bins,
        "live_advisory_origins": named,
    }


# --- the 2026 event -------------------------------------------------------------------
def first_version_origin(pub: dict[str, dict[str, Any]]) -> tuple[Origin, str, datetime]:
    first = pub[EVENT_2026_USGS_ID]["origin_versions"][0]
    origin = Origin(
        datetime.fromisoformat(first["event_time_utc"].replace("Z", "+00:00")),
        first["latitude"],
        first["longitude"],
        first["magnitude"],
        EVENT_2026_USGS_ID,
        "first published version",
    )
    return origin, first["event_type"], datetime.fromisoformat(first["published_utc"])


def event_2026(rows: list[Row], pub: dict[str, dict[str, Any]], scr: Screen) -> dict[str, Any]:
    now_origins = eligible(rows, scr)
    first, first_type, first_published = first_version_origin(pub)
    others = [r for r in rows if r.origin.event_id != EVENT_2026_USGS_ID]
    first_rows = sorted([*others, Row(first, first_type, "")], key=lambda r: r.origin.time_utc)
    first_origins = eligible(first_rows, scr)
    out: dict[str, Any] = {}
    for key, onset in EVENT_2026.items():
        site = SITES[key]
        today = explained_by(onset, now_origins, site, scr)
        later = explained_by(onset, first_origins, site, scr)
        known = [o for o in first_origins if o.event_id != EVENT_2026_USGS_ID]
        at_decision = explained_by(onset, known, site, scr)
        out[key] = {
            "set_aside_at_decision": at_decision.event_id if at_decision else None,
            "explained_by_first_published_version": later.event_id if later else None,
            "first_version_reaches_live_feed": later is not None
            and (first_published - first.time_utc).total_seconds() <= LOOKBACK_S
            and first.magnitude >= scr_fetch_min(scr),
            "explained_by_catalogue_now": today.event_id if today else None,
        }
    return out


def scr_fetch_min(scr: Screen) -> float:
    """The fetch threshold a screen needs: the live one, or lower for a lower tier."""
    return min(FEED_MIN_MAG, scr.near_mag if scr.near_mag is not None else FEED_MIN_MAG)


# --- live advisories ------------------------------------------------------------------
def live_times(rec: dict[str, Any]) -> tuple[list[datetime], str] | None:
    """The onset to judge first, then the other candidates it could have been."""
    if rec["onsets_utc"]:
        return [datetime.fromisoformat(t) for t in rec["onsets_utc"]], rec["onset_basis"]
    if rec["staged_utc"]:
        staged = datetime.fromisoformat(rec["staged_utc"])
        ts = [
            staged - timedelta(seconds=DECISION_AFTER_ONSET_S),
            staged - timedelta(seconds=DECISION_RANGE_S[0]),
            staged - timedelta(seconds=DECISION_RANGE_S[1]),
        ]
        return ts, "staged less 126 to 186 s"
    return None


def reaches_feed(
    origin: Origin, pub: dict[str, dict[str, Any]], fetch_min: float, lookback_s: float
) -> bool:
    """Would the live feed have held this origin's first version in time to explain?"""
    rec = pub.get(origin.event_id)
    if not rec or not rec["origin_versions"]:
        return False
    first = rec["origin_versions"][0]
    delay = (datetime.fromisoformat(first["published_utc"]) - origin.time_utc).total_seconds()
    return delay <= lookback_s and (first["magnitude"] or 0.0) >= fetch_min


def live_advisories(
    origins: list[Origin],
    origins_with_emsc: list[Origin],
    pub: dict[str, dict[str, Any]],
    scr: Screen,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for adv in LIVE_ADVISORIES:
        got = live_times(adv)
        if got is None:
            out.append({"id": adv["id"], "explained": None})
            continue
        times, basis = got
        hits = [explained_by(t, origins, KAKANI, scr) for t in times]
        hit = hits[0]
        with_emsc = explained_by(times[0], origins_with_emsc, KAKANI, scr)
        fetch_min = scr_fetch_min(scr)
        out.append(
            {
                "id": adv["id"],
                "time_basis": basis,
                "explained": hit is not None,
                "explained_over_whole_range": all(h is not None for h in hits),
                "by": hit.event_id if hit else None,
                "by_magnitude": hit.magnitude if hit else None,
                "by_distance_deg": round(
                    epicentral_distance_deg(KAKANI.latitude, KAKANI.longitude, hit), 1
                )
                if hit
                else None,
                "reaches_feed_2h": hit is not None
                and reaches_feed(hit, pub, fetch_min, LOOKBACK_S),
                "reaches_feed_7d": hit is not None
                and reaches_feed(hit, pub, fetch_min, LONG_LOOKBACK_S),
                "explained_with_emsc": with_emsc is not None,
                "with_emsc_by": with_emsc.event_id if with_emsc else None,
                "with_emsc_by_magnitude": with_emsc.magnitude if with_emsc else None,
            }
        )
    return out


def main() -> int:
    rows = load_catalogue()
    pub = publication(rows)
    emsc = load_emsc()
    with_emsc = sorted(rows + emsc, key=lambda r: r.origin.time_utc)
    corpora = noise_windows()
    all_screens = screens()
    results: dict[str, Any] = {
        "experiment": "exp035_regional_screen",
        "catalogue": {
            "source": "USGS ComCat",
            "period": [CATALOGUE[0].isoformat(), CATALOGUE[1].isoformat()],
            "regional": f"M{REGIONAL_MIN_MAG:g}+ within {REGIONAL_FETCH_DEG:g} deg of NK.KKN",
            "worldwide": "M5.0+",
            "origins": len(rows),
            "non_earthquake_types": sorted({r.event_type for r in rows} - {"earthquake"}),
        },
        "current_screen": {
            "min_magnitude": CURRENT.min_magnitude,
            "near_min_magnitude": CURRENT.near_min_magnitude,
            "near_deg": CURRENT.near_deg,
            "live_fetch_min_magnitude": FEED_MIN_MAG,
            "live_lookback_s": LOOKBACK_S,
        },
        "guard": {
            "protect_point": list(PROTECT_POINT),
            "protect_km": round(PROTECT_KM, 1),
            "margin_km": PROTECT_MARGIN_KM,
            "origins_inside_2025": {
                f"M{m:g}+": sum(
                    1
                    for r in rows
                    if YEAR[0] <= r.origin.time_utc < YEAR[1]
                    and r.origin.magnitude >= m
                    and protected(r.origin)
                )
                for m in (4.0, 4.4, 5.0)
            },
        },
        "emsc": {
            "periods": [
                [LIVE_PERIOD[0].isoformat(), LIVE_PERIOD[1].isoformat()],
                [EVENT_2026_HOURS[0].isoformat(), EVENT_2026_HOURS[1].isoformat()],
            ],
            "origins": len(emsc),
            "event_2026": [
                {
                    "id": r.origin.event_id,
                    "time_utc": r.origin.time_utc.isoformat(),
                    "magnitude": r.origin.magnitude,
                    "event_type": r.event_type,
                    "distance_deg_nk_kkn": round(
                        epicentral_distance_deg(KAKANI.latitude, KAKANI.longitude, r.origin), 2
                    ),
                }
                for r in emsc
                if EVENT_2026_HOURS[0] <= r.origin.time_utc < EVENT_2026_HOURS[1]
                and epicentral_distance_deg(KAKANI.latitude, KAKANI.longitude, r.origin) < 2.0
            ],
        },
        "year": [YEAR[0].isoformat(), YEAR[1].isoformat()],
        "screens": {},
    }
    noise_sizes = {k: {r: len(v) for r, v in c.items()} for k, c in corpora.items()}
    results["noise_corpus_windows"] = noise_sizes

    for scr in all_screens:
        origins = eligible(rows, scr)
        rec: dict[str, Any] = {
            "near_min_magnitude": scr.near_mag,
            "near_deg": scr.near_deg if scr.near_mag is not None else None,
            "guarded": scr.guarded,
            "fetch_min_magnitude_needed": scr_fetch_min(scr),
            "stations": {},
        }
        for key, site in SITES.items():
            wins = windows(origins, site, scr)
            year_fraction = covered_fraction(wins, *YEAR)
            noise = {}
            for corpus_name, corpus in corpora[key].items():
                noise[corpus_name] = {
                    "removed": removed(corpus, origins, site, scr),
                    "of": len(corpus),
                    "expected_by_chance": round(year_fraction * len(corpus), 1),
                }
            rec["stations"][key] = {
                "set_aside_fraction_2025": round(year_fraction, 4),
                "set_aside_fraction_live_fortnight": round(covered_fraction(wins, *LIVE_PERIOD), 4),
                "origins_counted_2025": sum(
                    1 for o in origins if YEAR[0] <= o.time_utc < YEAR[1] and counts(o, site, scr)
                ),
                "noise_false_alarm_windows": noise,
            }
        rec["live_advisories"] = live_advisories(origins, eligible(with_emsc, scr), pub, scr)
        timed = [x for x in rec["live_advisories"] if x["explained"] is not None]
        rec["live_advisories_summary"] = {
            "timed": len(timed),
            "explained_usgs_catalogue_now": sum(1 for x in timed if x["explained"]),
            "explained_in_operation_2h_lookback": sum(1 for x in timed if x["reaches_feed_2h"]),
            "explained_in_operation_7d_lookback": sum(1 for x in timed if x["reaches_feed_7d"]),
            "explained_usgs_or_emsc_catalogue_now": sum(
                1 for x in timed if x["explained_with_emsc"]
            ),
        }
        rec["event_2026"] = event_2026(rows, pub, scr)
        emsc_2026 = eligible(sorted(emsc, key=lambda r: r.origin.time_utc), scr)
        for key, onset in EVENT_2026.items():
            hit = explained_by(onset, emsc_2026, SITES[key], scr)
            rec["event_2026"][key]["explained_by_emsc_catalogue_now"] = (
                hit.event_id if hit else None
            )
        results["screens"][scr.name] = rec
        kkn = rec["stations"]["NK.KKN"]
        print(
            f"{scr.name:32s} KKN {kkn['set_aside_fraction_2025']:.3f} "
            f"EVN {rec['stations']['IO.EVN']['set_aside_fraction_2025']:.3f} "
            f"live {list(rec['live_advisories_summary'].values())} "
            f"2026 {rec['event_2026']['NK.KKN']}",
            flush=True,
        )

    first, first_type, first_published = first_version_origin(pub)
    results["event_2026_catalogue"] = {
        "usgs_id": EVENT_2026_USGS_ID,
        "first_published_utc": first_published.isoformat(),
        "first_version": {
            "time_utc": first.time_utc.isoformat(),
            "latitude": first.latitude,
            "longitude": first.longitude,
            "magnitude": first.magnitude,
            "event_type": first_type,
            "distance_deg_nk_kkn": round(
                epicentral_distance_deg(KAKANI.latitude, KAKANI.longitude, first), 2
            ),
        },
        "minutes_after_decision": round(
            (first_published - EVENT_2026_DECISION).total_seconds() / 60.0, 1
        ),
        "versions": pub[EVENT_2026_USGS_ID]["origin_versions"],
    }
    results["publication"] = latency_summary(rows, pub)
    results["live_advisory_records"] = LIVE_ADVISORIES
    out = HERE / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"results -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
