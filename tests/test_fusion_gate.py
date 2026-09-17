"""Issue #26: whether a quiet but live channel may count toward the WARNING gate."""

from __future__ import annotations

from dataclasses import replace

from ghadi.config import DEFAULT
from ghadi.fusion import Channel, Tier, fuse

HISTORICAL = replace(DEFAULT.fusion, warning_requires_supporting_groups=False)
STRICT = DEFAULT.fusion


def gauge_surge() -> Channel:
    return Channel("gauge", DEFAULT.fusion.hydro_detected_p, independence_group="hydro")


def seismic_quiet() -> Channel:
    return Channel("seismic", DEFAULT.fusion.seismic_quiet_p, independence_group="seismic")


def seismic_detected() -> Channel:
    return Channel("seismic", DEFAULT.fusion.seismic_detected_p, independence_group="seismic")


def test_strict_rule_is_the_default() -> None:
    """Chosen by the project owner after exp017."""
    assert DEFAULT.fusion.warning_requires_supporting_groups is True


def test_historical_rule_lets_a_quiet_second_sensor_raise_the_tier() -> None:
    """The behaviour #26 describes, kept behind the flag and pinned."""
    alone = fuse([gauge_surge()], HISTORICAL)
    with_quiet = fuse([gauge_surge(), seismic_quiet()], HISTORICAL)
    assert alone.tier is Tier.ADVISORY
    assert with_quiet.tier is Tier.WARNING
    assert with_quiet.independent_groups == 2 and with_quiet.supporting_groups == 1


def test_strict_rule_does_not_let_a_quiet_sensor_raise_the_tier() -> None:
    alone = fuse([gauge_surge()], STRICT)
    with_quiet = fuse([gauge_surge(), seismic_quiet()], STRICT)
    assert alone.tier is Tier.ADVISORY
    assert with_quiet.tier is Tier.ADVISORY
    assert "1 supporting group" in with_quiet.rationale


def test_both_rules_warn_when_two_independent_sources_detect() -> None:
    for cfg in (HISTORICAL, STRICT):
        d = fuse([gauge_surge(), seismic_detected()], cfg)
        assert d.tier is Tier.WARNING
        assert d.supporting_groups == 2


def test_supporting_groups_ignores_dead_channels_and_duplicates() -> None:
    dead = Channel("gauge", 0.8, independence_group="hydro", alive=False)
    mirror = Channel("seismic_mirror", 0.6, independence_group="seismic")
    d = fuse([seismic_detected(), mirror, dead], STRICT)
    assert d.supporting_groups == 1
    assert d.tier is not Tier.WARNING
