"""Judging an event pair against its same-track pre-event control.

In high mountains most 12-day radar pairs show some changed patch, event or not. The
control comparison is what stops seasonal change from being reported as a confirmation.
"""

from __future__ import annotations

import pytest

from ghadi.config import DEFAULT, EoConfig
from ghadi.eo import compare_to_control


def test_event_well_above_control_is_confirmed() -> None:
    c = compare_to_control("change_detected", 5.0, "change_detected", 2.0)
    assert c.verdict == "above_background"
    assert c.ratio == pytest.approx(2.5)


def test_event_smaller_than_control_is_seasonal_background() -> None:
    # Langtang 2015, orbit 85: the control showed more change than the event pair.
    c = compare_to_control("change_detected", 3.904, "change_detected", 12.83)
    assert c.verdict == "within_background"
    assert "seasonal change" in c.reason


def test_event_just_under_the_ratio_floor_is_not_confirmed() -> None:
    c = compare_to_control("change_detected", 3.9, "change_detected", 2.0)  # 1.95x
    assert c.verdict == "within_background"


def test_change_with_an_empty_control_is_above_background() -> None:
    c = compare_to_control("change_detected", 0.5, "no_change", 0.0)
    assert c.verdict == "above_background"
    assert c.ratio is None


def test_no_event_change_is_within_background() -> None:
    c = compare_to_control("no_change", 0.01, "change_detected", 1.0)
    assert c.verdict == "within_background"
    assert "no changed patch" in c.reason


def test_an_unjudgeable_pair_makes_the_comparison_inconclusive() -> None:
    assert compare_to_control("inconclusive", 1.0, "no_change", 0.0).verdict == "inconclusive"
    assert compare_to_control("change_detected", 9.0, "inconclusive", 0.0).verdict == "inconclusive"


def test_ratio_floor_is_configurable_and_defaults_to_two() -> None:
    assert DEFAULT.eo.control_min_ratio == 2.0
    strict = EoConfig(control_min_ratio=3.0)
    assert compare_to_control("change_detected", 5.0, "change_detected", 2.0, strict).verdict == (
        "within_background"
    )
