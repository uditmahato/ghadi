"""DHM gauge-telemetry ingestion: cleaning, liveness, and the path into the detector."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from ghadi.config import DEFAULT, DhmConfig
from ghadi.dhm import GaugeSeries, ingest, parse_csv
from ghadi.fusion import channel_from_hydro
from ghadi.hydro import detect_anomaly, synthetic_surge

BASE = datetime(2026, 8, 26, 3, 0, 0, tzinfo=UTC)


def _times(n: int, step_s: float = 300.0) -> list[datetime]:
    return [BASE + timedelta(seconds=i * step_s) for i in range(n)]


def test_clean_series_passes_through_in_metres() -> None:
    ts = _times(5)
    series = ingest(ts, [2.0, 2.1, 2.0, 2.2, 2.1], unit="m", as_of=ts[-1])
    assert series.n_dropped == 0
    assert series.stage_m.tolist() == pytest.approx([2.0, 2.1, 2.0, 2.2, 2.1])
    # Times are relative to the first sample.
    assert series.times_s.tolist() == pytest.approx([0.0, 300.0, 600.0, 900.0, 1200.0])
    assert series.origin_utc == BASE


def test_centimetre_unit_is_converted_and_datum_applied() -> None:
    series = ingest(_times(3), [200.0, 210.0, 205.0], unit="cm", datum_offset_m=1.0)
    # 200 cm -> 2.0 m, + 1.0 datum = 3.0 m.
    assert series.stage_m.tolist() == pytest.approx([3.0, 3.1, 3.05])


def test_sentinels_and_non_finite_are_masked_and_counted() -> None:
    ts = _times(5)
    series = ingest(ts, [2.0, -9999.0, 2.1, float("nan"), 2.2])
    assert series.stage_m.tolist() == pytest.approx([2.0, 2.1, 2.2])
    assert series.dropped["sentinel"] == 1
    assert series.dropped["nan_or_inf"] == 1
    assert series.n_dropped == 2


def test_implausible_readings_are_dropped_not_clipped() -> None:
    series = ingest(_times(3), [2.0, 500.0, 2.1])  # 500 m is not a river stage
    assert series.stage_m.tolist() == pytest.approx([2.0, 2.1])
    assert series.dropped["implausible_stage"] == 1


def test_out_of_order_timestamps_are_sorted() -> None:
    ts = [BASE + timedelta(seconds=s) for s in (600, 0, 300)]
    series = ingest(ts, [2.2, 2.0, 2.1])
    assert series.times_s.tolist() == pytest.approx([0.0, 300.0, 600.0])
    assert series.stage_m.tolist() == pytest.approx([2.0, 2.1, 2.2])


def test_duplicate_timestamp_keeps_the_later_packet() -> None:
    ts = [BASE, BASE, BASE + timedelta(seconds=300)]
    series = ingest(ts, [2.0, 2.5, 2.6])  # second reading at BASE supersedes the first
    assert series.stage_m.tolist() == pytest.approx([2.5, 2.6])
    assert series.dropped["duplicate_timestamp"] == 1


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ingest([datetime(2026, 8, 26, 3, 0, 0)], [2.0])


def test_fresh_gauge_is_alive_stale_gauge_is_dead() -> None:
    ts = _times(4)
    alive = ingest(ts, [2, 2, 2, 2], as_of=ts[-1] + timedelta(seconds=300))
    assert alive.sensor_alive is True
    # Newest sample far older than staleness_factor * expected interval.
    dead = ingest(ts, [2, 2, 2, 2], as_of=ts[-1] + timedelta(seconds=3000))
    assert dead.sensor_alive is False
    assert any("declared dead" in w for w in dead.warnings)


def test_liveness_is_unassessed_without_as_of() -> None:
    series = ingest(_times(4), [2, 2, 2, 2])
    assert series.sensor_alive is None


def test_empty_after_cleaning_is_dead_with_as_of_unknown_without() -> None:
    dead = ingest(_times(2), [-9999.0, -9999.0], as_of=BASE + timedelta(seconds=600))
    assert dead.sensor_alive is False
    assert dead.times_s.size == 0
    unknown = ingest(_times(2), [-9999.0, -9999.0])
    assert unknown.sensor_alive is None


def test_coarse_sampling_and_internal_gap_warn() -> None:
    coarse = ingest(_times(4, step_s=1200.0), [2, 2, 2, 2])  # 20-min sampling
    assert any("coarser" in w for w in coarse.warnings)
    ts = [BASE, BASE + timedelta(seconds=300), BASE + timedelta(seconds=5000)]
    gappy = ingest(ts, [2, 2, 2])
    assert any("gap" in w for w in gappy.warnings)


def test_median_interval_is_reported() -> None:
    series = ingest(_times(5, step_s=300.0), [2, 2, 2, 2, 2])
    assert series.median_interval_s == pytest.approx(300.0)


def test_a_real_format_surge_flows_through_to_a_detection() -> None:
    # Build a Trishuli-scale surge, then dress it as a raw DHM export: 5-min sampling,
    # centimetres, a sentinel dropout and a duplicated packet. Ingest must recover a
    # series the detector fires on.
    t_s, stage_m = synthetic_surge(sample_interval_s=300.0)
    timestamps = [BASE + timedelta(seconds=float(t)) for t in t_s]
    values_cm = [float(s * 100.0) for s in stage_m]
    values_cm[3] = -9999.0  # a dropout partway through the quiet baseline
    timestamps.append(timestamps[10])  # a duplicated packet
    values_cm.append(values_cm[10])

    series = ingest(timestamps, values_cm, unit="cm", as_of=timestamps[-2])
    assert series.dropped.get("sentinel") == 1
    assert series.dropped.get("duplicate_timestamp") == 1

    times, stage = series.detector_input()
    result = detect_anomaly(times, stage)
    assert result.detected

    # And the ingestion-layer liveness fact flows into fusion untouched.
    channel = channel_from_hydro(result, sensor_alive=bool(series.sensor_alive))
    assert channel.alive


def test_dead_sensor_after_a_rise_still_corroborates() -> None:
    # The gauge saw the leading edge, then the surge destroyed it. Detection stands and
    # the channel is live because the anomaly was recorded before the sensor died.
    t_s, stage_m = synthetic_surge(sample_interval_s=300.0, destroy_at_s=2100.0)
    timestamps = [BASE + timedelta(seconds=float(t)) for t in t_s]
    values = [float(s) for s in stage_m]
    # as_of is well after the last packet: ingestion correctly sees a dead sensor.
    series = ingest(timestamps, values, as_of=BASE + timedelta(seconds=10000))
    assert series.sensor_alive is False
    result = detect_anomaly(*series.detector_input())
    channel = channel_from_hydro(result, sensor_alive=bool(series.sensor_alive))
    # Detection despite a dead sensor => the channel is alive (a recorded anomaly).
    assert result.detected and channel.alive


def test_parse_csv_reads_iso_rows_and_skips_bad_ones() -> None:
    text = (
        "timestamp,stage_m\n"
        "2026-08-26T03:00:00+05:45,2.0\n"
        "2026-08-26T03:05:00+05:45,2.1\n"
        "garbage,line\n"
        "2026-08-26T03:10:00+05:45,2.2\n"
    )
    ts, vals = parse_csv(text)
    assert len(ts) == 3 and vals == pytest.approx([2.0, 2.1, 2.2])
    # The parsed NPT timestamps survive ingestion into a clean series.
    series = ingest(ts, vals)
    assert series.stage_m.tolist() == pytest.approx([2.0, 2.1, 2.2])


def test_parse_csv_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="explicit"):
        parse_csv("t,s\n2026-08-26T03:00:00,2.0\n")


def test_config_exposes_dhm() -> None:
    assert isinstance(DEFAULT.dhm, DhmConfig)


def test_gauge_series_detector_input_roundtrips() -> None:
    series: GaugeSeries = ingest(_times(3), [2.0, 2.1, 2.2])
    times, stage = series.detector_input()
    assert isinstance(times, np.ndarray) and isinstance(stage, np.ndarray)
    assert times.size == stage.size == 3
