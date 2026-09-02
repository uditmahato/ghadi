"""Catalogue schema validation. The load-bearing rule: origin_uncertainty_s > 0."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ghadi.catalog import CatalogError, load_catalog, load_event

VALID = {
    "event_id": "TEST-0001",
    "origin_utc": "2026-08-26T02:52:10Z",
    "origin_uncertainty_s": 15,
    "time_source": "seismic",
    "label": "mass_movement",
    "lat": 28.255,
    "lon": 85.520,
    "location_uncertainty_km": 8.0,
}


def _write(tmp_path: Path, **overrides: object) -> Path:
    data = {**VALID, **overrides}
    path = tmp_path / "event.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_valid_event_loads(tmp_path: Path) -> None:
    event = load_event(_write(tmp_path))
    assert event.event_id == "TEST-0001"
    assert event.origin_utc.tzinfo is not None


def test_zero_origin_uncertainty_is_rejected(tmp_path: Path) -> None:
    # HANDOFF §5.3: zero is forbidden. No event time is known exactly, and a
    # news-derived time with zero uncertainty is the specific failure guarded here.
    with pytest.raises(CatalogError, match="strictly positive"):
        load_event(_write(tmp_path, origin_uncertainty_s=0))


def test_naive_timestamp_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="timezone-aware"):
        load_event(_write(tmp_path, origin_utc="2026-08-26T02:52:10"))


def test_unknown_label_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="label must be one of"):
        load_event(_write(tmp_path, label="probably_a_landslide"))


def test_deaths_without_a_status_is_rejected(tmp_path: Path) -> None:
    # An impact figure without CONFIRMED/PROVISIONAL/ESTIMATE is meaningless.
    with pytest.raises(CatalogError, match="deaths_status"):
        load_event(_write(tmp_path, deaths=1058))


def test_shipped_catalog_is_valid_and_has_the_seed_events() -> None:
    events = load_catalog()
    assert len(events) >= 6
    ids = {e.event_id for e in events}
    assert "NPL-2026-08-26-BHOTEKOSHI-001" in ids
    assert all(e.origin_uncertainty_s > 0 for e in events)
    assert all(e.origin_utc.tzinfo is not None for e in events)


def test_news_derived_times_carry_coarse_uncertainty() -> None:
    # A news report never pins an origin to the second. Anything under a minute on a
    # news-derived time is false precision and should be caught in review.
    for event in load_catalog():
        if event.time_source == "news":
            assert event.origin_uncertainty_s >= 60
