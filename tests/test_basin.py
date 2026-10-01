"""The catchment outline: the 2026 source is inside it, the stations are not."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ghadi.basin import Basin, load_basin
from ghadi.config import EVEREST, KAKANI, SOURCE_ZONE_LAT, SOURCE_ZONE_LON, TRISHULI_R07


def test_the_committed_outline_loads_and_is_closed() -> None:
    basin = load_basin()
    assert basin.lons[0] == basin.lons[-1] and basin.lats[0] == basin.lats[-1]
    assert 4000 < basin.area_km2 < 5500, "the Trishuli above Bidur is about 4,700 km2"


def test_the_2026_source_is_inside_and_the_stations_are_outside() -> None:
    basin = load_basin()
    assert bool(basin.contains(SOURCE_ZONE_LAT, SOURCE_ZONE_LON)[0])
    assert not bool(basin.contains(KAKANI.latitude, KAKANI.longitude)[0])
    assert not bool(basin.contains(EVEREST.latitude, EVEREST.longitude)[0])


def test_the_upstream_settlements_are_inside() -> None:
    basin = load_basin()
    upstream = [s for s in TRISHULI_R07.settlements if s.name in ("Timure", "Syabrubesi")]
    assert upstream
    for s in upstream:
        assert bool(basin.contains(s.lat, s.lon)[0]), s.name


def test_contains_is_vectorised_and_uses_the_even_odd_rule(tmp_path: Path) -> None:
    square = {
        "type": "Feature",
        "properties": {"name": "square", "area_km2": 1.0},
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]},
    }
    path = tmp_path / "sq.geojson"
    path.write_text(json.dumps(square))
    basin: Basin = load_basin(path)
    got = basin.contains(np.array([1.0, 3.0, 1.0, -1.0]), np.array([1.0, 1.0, 3.0, 1.0]))
    assert got.tolist() == [True, False, False, False]
    assert basin.bounds == (0.0, 2.0, 0.0, 2.0)
