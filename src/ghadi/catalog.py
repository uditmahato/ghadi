"""The Himalayan Mass-Movement Seismic Event Catalogue.

Committed event definitions live in ``data/catalog/*.yaml`` and are validated on load
against the schema in HANDOFF §6.3. The two rules that are enforced hard:

- every ``origin_utc`` is timezone-aware and stored as UTC;
- ``origin_uncertainty_s`` is strictly positive — no event time is ever known exactly,
  and zero on a news-derived time is the specific failure the handoff forbids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

VALID_LABELS = frozenset({"mass_movement", "earthquake", "noise", "unknown"})
VALID_TIME_SOURCES = frozenset({"instrumental", "seismic", "news"})
VALID_FIGURE_STATUS = frozenset({"CONFIRMED", "PROVISIONAL", "ESTIMATE"})


class CatalogError(ValueError):
    """A catalogue entry violated the schema."""


@dataclass(frozen=True)
class CatalogEvent:
    event_id: str
    origin_utc: datetime
    origin_uncertainty_s: float
    time_source: str  # instrumental | seismic | news
    label: str  # mass_movement | earthquake | noise | unknown
    lat: float
    lon: float
    location_uncertainty_km: float
    hazard_subtype: str | None = None
    river_system: str | None = None
    deaths: int | None = None
    missing: int | None = None
    deaths_status: str | None = None  # CONFIRMED | PROVISIONAL | ESTIMATE
    sources: tuple[str, ...] = ()
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _require(condition: bool, path: Path, message: str) -> None:
    if not condition:
        raise CatalogError(f"{path.name}: {message}")


def _parse_origin(raw: Any, path: Path) -> datetime:
    if isinstance(raw, datetime):
        origin = raw
    elif isinstance(raw, str):
        try:
            origin = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CatalogError(f"{path.name}: unparseable origin_utc {raw!r}") from exc
    else:
        raise CatalogError(f"{path.name}: origin_utc must be an ISO-8601 string")
    _require(
        origin.tzinfo is not None,
        path,
        "origin_utc must be timezone-aware (append 'Z' or an offset)",
    )
    return origin.astimezone(UTC)


def load_event(path: Path) -> CatalogEvent:
    """Load and validate a single catalogue entry."""
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    _require(isinstance(raw, dict), path, "top level must be a mapping")

    known = {
        "event_id",
        "origin_utc",
        "origin_uncertainty_s",
        "time_source",
        "label",
        "lat",
        "lon",
        "location_uncertainty_km",
        "hazard_subtype",
        "river_system",
        "deaths",
        "missing",
        "deaths_status",
        "sources",
        "notes",
    }
    for req in ("event_id", "origin_utc", "origin_uncertainty_s", "time_source", "label"):
        _require(req in raw, path, f"missing required field {req!r}")

    origin = _parse_origin(raw["origin_utc"], path)

    uncertainty = float(raw["origin_uncertainty_s"])
    _require(
        uncertainty > 0,
        path,
        "origin_uncertainty_s must be strictly positive — zero is forbidden "
        "(no event time is known exactly; HANDOFF §5.3)",
    )

    time_source = str(raw["time_source"])
    _require(
        time_source in VALID_TIME_SOURCES,
        path,
        f"time_source must be one of {sorted(VALID_TIME_SOURCES)}",
    )

    label = str(raw["label"])
    _require(label in VALID_LABELS, path, f"label must be one of {sorted(VALID_LABELS)}")

    deaths_status = raw.get("deaths_status")
    if raw.get("deaths") is not None:
        _require(
            deaths_status in VALID_FIGURE_STATUS,
            path,
            "deaths given without a deaths_status (CONFIRMED | PROVISIONAL | ESTIMATE) — "
            "an impact figure without a status is meaningless",
        )

    for coord in ("lat", "lon", "location_uncertainty_km"):
        _require(coord in raw, path, f"missing required field {coord!r}")

    return CatalogEvent(
        event_id=str(raw["event_id"]),
        origin_utc=origin,
        origin_uncertainty_s=uncertainty,
        time_source=time_source,
        label=label,
        lat=float(raw["lat"]),
        lon=float(raw["lon"]),
        location_uncertainty_km=float(raw["location_uncertainty_km"]),
        hazard_subtype=raw.get("hazard_subtype"),
        river_system=raw.get("river_system"),
        deaths=raw.get("deaths"),
        missing=raw.get("missing"),
        deaths_status=deaths_status,
        sources=tuple(raw.get("sources", ())),
        notes=raw.get("notes"),
        extra={k: v for k, v in raw.items() if k not in known},
    )


def default_catalog_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "catalog"


def load_catalog(directory: Path | None = None) -> list[CatalogEvent]:
    """Load every entry in the catalogue directory, sorted by origin time."""
    directory = directory or default_catalog_dir()
    events = [load_event(p) for p in sorted(directory.glob("*.yaml"))]
    ids = [e.event_id for e in events]
    if len(ids) != len(set(ids)):
        raise CatalogError("duplicate event_id in catalogue")
    return sorted(events, key=lambda e: e.origin_utc)
