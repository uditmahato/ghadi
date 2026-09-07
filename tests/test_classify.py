"""The seismic physics detector and its bridge into fusion."""

from __future__ import annotations

import math

import pytest

from ghadi.classify import classify_segment
from ghadi.config import DEFAULT, ClassifyConfig
from ghadi.fusion import Tier, channel_from_hydro, channel_from_seismic, fuse
from ghadi.hydro import detect_anomaly, synthetic_surge

# Cascade decision-segment values (exp005) and the earthquake corpus medians.
CASCADE_LF_HF = 4.9188
CASCADE_CENTROID = 1.8852
EQ_MEDIAN_LF_HF = 1.66
EQ_MEDIAN_CENTROID = 3.04


def test_cascade_values_are_classified_mass_movement_like() -> None:
    c = classify_segment(CASCADE_LF_HF, CASCADE_CENTROID)
    assert c.mass_movement_like


def test_typical_earthquake_is_not_mass_movement_like() -> None:
    c = classify_segment(EQ_MEDIAN_LF_HF, EQ_MEDIAN_CENTROID)
    assert not c.mass_movement_like


def test_rule_is_a_conjunction_one_feature_is_not_enough() -> None:
    # Low-frequency centroid but earthquake-like LF/HF => not enough.
    assert not classify_segment(1.5, CASCADE_CENTROID).mass_movement_like
    # High LF/HF but earthquake-like centroid => not enough.
    assert not classify_segment(CASCADE_LF_HF, 3.5).mass_movement_like


def test_threshold_boundary_is_inclusive() -> None:
    cfg = DEFAULT.classify
    c = classify_segment(cfg.cascade_segment_lf_hf, cfg.cascade_segment_centroid_hz)
    assert c.mass_movement_like  # >= and <= are inclusive at the cascade's own values


def test_nan_feature_fails_the_rule() -> None:
    # A NaN feature means the signal-presence gate found nothing to measure; absence of
    # a measurable low-frequency source is not evidence of one.
    assert not classify_segment(math.nan, CASCADE_CENTROID).mass_movement_like
    assert not classify_segment(CASCADE_LF_HF, math.nan).mass_movement_like


def test_reason_carries_the_overlap_and_the_lower_bound_caveat() -> None:
    c = classify_segment(CASCADE_LF_HF, CASCADE_CENTROID)
    assert "17.2%" in c.reason
    assert "lower bound" in c.reason and "n=1" in c.reason


def test_overlap_is_the_measured_11_of_64() -> None:
    assert DEFAULT.classify.earthquake_overlap == pytest.approx(11.0 / 64.0)


def test_channel_from_a_positive_classification_is_alive_and_detected() -> None:
    c = classify_segment(CASCADE_LF_HF, CASCADE_CENTROID)
    ch = channel_from_seismic(c)
    assert ch.alive
    assert ch.probability == pytest.approx(DEFAULT.fusion.seismic_detected_p)
    assert ch.independence_group == "upstream_seismic"


def test_offline_station_with_no_classification_is_a_dead_channel() -> None:
    c = classify_segment(EQ_MEDIAN_LF_HF, EQ_MEDIAN_CENTROID)
    ch = channel_from_seismic(c, sensor_alive=False)
    assert not ch.alive  # absence cannot be concluded from a dead station
    assert "dead station" in ch.detail


def test_quiet_live_station_is_a_live_low_probability_channel() -> None:
    c = classify_segment(EQ_MEDIAN_LF_HF, EQ_MEDIAN_CENTROID)
    ch = channel_from_seismic(c, sensor_alive=True)
    assert ch.alive
    assert ch.probability == pytest.approx(DEFAULT.fusion.seismic_quiet_p)


def test_positive_classification_stands_even_if_station_later_died() -> None:
    c = classify_segment(CASCADE_LF_HF, CASCADE_CENTROID)
    ch = channel_from_seismic(c, sensor_alive=False)
    assert ch.alive  # evidence already computed from a window that existed


def test_seismic_is_weaker_corroboration_than_hydro_alone() -> None:
    # Same design intent as the config comment: the seismic channel on its own must not
    # reach as high a fused probability as a gauge surge, given the 17.2% overlap.
    seismic = channel_from_seismic(classify_segment(CASCADE_LF_HF, CASCADE_CENTROID))
    hydro = channel_from_hydro(detect_anomaly(*synthetic_surge()))
    assert fuse([seismic]).probability < fuse([hydro]).probability


def test_both_channels_firing_reach_a_warning() -> None:
    seismic = channel_from_seismic(classify_segment(CASCADE_LF_HF, CASCADE_CENTROID))
    hydro = channel_from_hydro(detect_anomaly(*synthetic_surge()))
    decision = fuse([seismic, hydro])
    # Two independent groups both firing clears the WARNING bar.
    assert decision.tier is Tier.WARNING
    assert decision.independent_groups == 2


def test_config_exposes_classify_and_seismic_operating_points() -> None:
    assert isinstance(DEFAULT.classify, ClassifyConfig)
    assert 0.0 <= DEFAULT.fusion.seismic_detected_p <= 1.0
    assert DEFAULT.fusion.seismic_detected_p < DEFAULT.fusion.hydro_detected_p
