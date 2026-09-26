"""Experiment 017: where do the two WARNING gate rules disagree? (issue #26)

**Question.** The WARNING tier needs at least two independent evidence groups. Under the
historical rule any *live* group counts, including one that is reporting but quiet.
Under the strict rule only *supporting* groups count, those that actually detected
something. Before choosing, what exactly changes: in which sensor states do the rules
disagree, does either rule ever let a quiet sensor raise the alert level, and what
happens to the dashboard scenarios and the one real event?

**Design.** Fully offline and exhaustive. Every combination of one seismic channel and
one or two gauge channels, each in every state the pipeline can produce (absent; dead
with no detection; live and quiet; live and detected), is turned into fusion channels by
the real ``channel_from_*`` functions and fused under both rules. Then:

1. **Disagreements.** Every state where the tiers differ is listed.
2. **Monotonicity.** Adding a live, quiet channel from a new independent group should
   never raise the tier: a sensor reporting "nothing here" is not corroboration. Every
   state is tested under both rules.
3. **Scenarios.** The dashboard presets, which include the 2026 case, are run through
   ``ghadi.service.process_window`` under both rules.

    python experiments/exp017_fusion_warning_gate/run.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import timedelta
from itertools import product
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ghadi.classify import classify_segment  # noqa: E402
from ghadi.config import DEFAULT, GhadiConfig  # noqa: E402
from ghadi.fusion import (  # noqa: E402
    Channel,
    Tier,
    channel_from_hydro,
    channel_from_seismic,
    fuse,
)
from ghadi.hydro import HydroAnomaly  # noqa: E402
from ghadi.service import WindowObservation, process_window  # noqa: E402
from ghadi.teleseism import Origin  # noqa: E402

RULES = {
    "historical": replace(DEFAULT.fusion, warning_requires_supporting_groups=False),
    "strict": replace(DEFAULT.fusion, warning_requires_supporting_groups=True),
}
ORDER = {Tier.NONE: 0, Tier.WATCH: 1, Tier.ADVISORY: 2, Tier.WARNING: 3}
STATES = ("absent", "dead", "quiet", "detected")


def _anomaly(detected: bool) -> HydroAnomaly:
    return HydroAnomaly(
        detected=detected,
        time_s=1740.0 if detected else None,
        peak_rate_m_per_min=0.3 if detected else 0.01,
        robust_z=9.0 if detected else 0.5,
        reason="synthetic state",
        n_samples=60,
        truncated=False,
    )


def seismic_channel(state: str) -> Channel | None:
    if state == "absent":
        return None
    like = state == "detected"
    cls = classify_segment(4.9188 if like else 1.66, 1.8852 if like else 3.04)
    return channel_from_seismic(cls, sensor_alive=state != "dead")


def gauge_channel(state: str, name: str, group: str) -> Channel | None:
    if state == "absent":
        return None
    return channel_from_hydro(
        _anomaly(state == "detected"),
        sensor_alive=state != "dead",
        name=name,
        independence_group=group,
    )


def tiers(channels: list[Channel]) -> dict[str, str]:
    return {rule: fuse(channels, cfg).tier.value for rule, cfg in RULES.items()}


def main() -> None:
    rows: list[dict[str, Any]] = []
    violations: dict[str, list[dict[str, Any]]] = {r: [] for r in RULES}

    # Two gauges on the same river share one independence group, as in service.
    for s_state, g1_state, g2_state in product(STATES, STATES, STATES):
        chans = [
            c
            for c in (
                seismic_channel(s_state),
                gauge_channel(g1_state, "gauge_timure", "downstream_gauge"),
                gauge_channel(g2_state, "gauge_syabrubesi", "downstream_gauge"),
            )
            if c is not None
        ]
        decisions = {rule: fuse(chans, cfg) for rule, cfg in RULES.items()}
        row = {
            "seismic": s_state,
            "gauge_1": g1_state,
            "gauge_2": g2_state,
            "fused_p": round(decisions["historical"].probability, 3),
            "live_groups": decisions["historical"].independent_groups,
            "supporting_groups": decisions["historical"].supporting_groups,
            **{f"tier_{rule}": d.tier.value for rule, d in decisions.items()},
        }
        row["differs"] = row["tier_historical"] != row["tier_strict"]
        rows.append(row)

        # Monotonicity: add a live quiet channel from a brand-new independent group.
        extra = Channel("extra_quiet", DEFAULT.fusion.seismic_quiet_p, independence_group="extra")
        for rule, cfg in RULES.items():
            before = fuse(chans, cfg).tier
            after = fuse([*chans, extra], cfg).tier
            if ORDER[after] > ORDER[before]:
                violations[rule].append(
                    {
                        "seismic": s_state,
                        "gauge_1": g1_state,
                        "gauge_2": g2_state,
                        "tier_before": before.value,
                        "tier_after_adding_quiet_channel": after.value,
                    }
                )

    differing = [r for r in rows if r["differs"]]

    # Dashboard presets through the real service, under both rules.
    import serve  # scripts/serve.py: the presets and how they build observations

    scenarios = []
    for label, qs, _desc in serve.PRESETS:
        q = dict(pair.split("=", 1) for pair in qs.split("&"))
        inp, errors = serve._validate(q)
        assert inp is not None and not errors, (label, errors)
        entry: dict[str, Any] = {"scenario": label}
        for rule, fcfg in RULES.items():
            cfg = replace(GhadiConfig(), fusion=fcfg)
            origins: tuple[Origin, ...] = ()
            if inp.teleseism:
                origins = (
                    Origin(
                        time_utc=serve.EVENT_TIME,
                        latitude=serve.PRIMARY_STATION_LAT,
                        longitude=serve.PRIMARY_STATION_LON,
                        magnitude=6.5,
                    ),
                )
            obs = WindowObservation(
                window_start_utc=serve.EVENT_TIME - timedelta(seconds=120),
                detected_utc=serve.EVENT_TIME,
                segment_lf_hf=inp.lf_hf,
                segment_centroid_hz=inp.centroid,
                seismic_sensor_alive=inp.station_alive,
                gauge=serve._gauge_obs(inp.gauge),
                origins=origins,
                event_id="SCENARIO",
            )
            o = process_window(
                obs,
                reach=serve.REACH_ID,
                model_version="exp017",
                warning_latency_s=inp.latency,
                config=cfg,
            )
            entry[f"tier_{rule}"] = o.decision.tier.value
            entry[f"supporting_groups_{rule}"] = o.decision.supporting_groups
            entry["live_groups"] = o.decision.independent_groups
            entry["fused_p"] = round(o.decision.probability, 3)
        entry["differs"] = entry["tier_historical"] != entry["tier_strict"]
        scenarios.append(entry)

    results = {
        "experiment": "exp017_fusion_warning_gate",
        "operating_points": {
            "seismic_detected_p": DEFAULT.fusion.seismic_detected_p,
            "seismic_quiet_p": DEFAULT.fusion.seismic_quiet_p,
            "hydro_detected_p": DEFAULT.fusion.hydro_detected_p,
            "hydro_quiet_p": DEFAULT.fusion.hydro_quiet_p,
            "support_p": DEFAULT.fusion.support_p,
            "warning_p": DEFAULT.fusion.warning_p,
            "advisory_p": DEFAULT.fusion.advisory_p,
            "min_groups_for_warning": DEFAULT.fusion.min_groups_for_warning,
        },
        "n_states": len(rows),
        "n_differing": len(differing),
        "differing_states": differing,
        "monotonicity_violations": {r: v for r, v in violations.items()},
        "scenarios": scenarios,
        "all_states": rows,
    }
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"{len(rows)} sensor states; tiers differ in {len(differing)}")
    for r in differing:
        print(
            f"  seismic={r['seismic']:<8} gauge1={r['gauge_1']:<8} gauge2={r['gauge_2']:<8} "
            f"p={r['fused_p']:.3f} live={r['live_groups']} supporting={r['supporting_groups']}: "
            f"historical {r['tier_historical']} -> strict {r['tier_strict']}"
        )
    for rule, v in violations.items():
        print(f"monotonicity violations under {rule}: {len(v)}")
        for x in v[:6]:
            print(f"   {x}")
    print("scenarios:")
    for s in scenarios:
        flag = "  <- differs" if s["differs"] else ""
        print(
            f"  {s['scenario']:<32} p={s['fused_p']:.3f} historical {s['tier_historical']:<8} "
            f"strict {s['tier_strict']}{flag}"
        )
    print(f"results -> {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
