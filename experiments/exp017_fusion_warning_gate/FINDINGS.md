# Experiment 017: where do the two WARNING gate rules disagree? (issue #26)

**Question.** A WARNING needs at least two independent evidence groups. Under the
historical rule any *live* group counts, including one that is reporting but quiet.
Under the strict rule only *supporting* groups count: groups whose strongest channel
actually detected something. Before choosing, what exactly changes?

**Answer.** The rules disagree in one situation only, and in that situation the
historical rule breaks a basic property.

* **Seven of 64 sensor states differ, and they are all the same case:** a gauge detects a
  surge while the seismic station is online and quiet. The historical rule gives WARNING
  (fused score 0.81, two live groups, one of them detecting). The strict rule gives
  ADVISORY. Every other state, including every state where both sources detect, is
  identical under both rules.
* **The historical rule lets a quiet sensor raise the alert level.** Adding a live,
  quiet channel from a new independent group raised the tier from ADVISORY to WARNING in
  **14 states** under the historical rule, and in **0** under the strict rule. A gauge
  surge on its own is ADVISORY; the same surge with a quiet seismometer switched on is
  WARNING. The second sensor is reporting "nothing here", which is the opposite of
  corroboration, and it is the only reason the tier went up.
* **The 2026 event is unaffected.** It is WARNING under both rules, because both sources
  detect. Of the six dashboard scenarios only "Regional earthquake with surge" changes,
  from WARNING to ADVISORY.

Run 2026-09-17, fully offline, deterministic.

## Design

Every combination of one seismic channel and two gauge channels, each in every state the
pipeline can produce (absent; dead with no detection; live and quiet; live and detected),
built by the real `channel_from_seismic` and `channel_from_hydro` and fused under both
rules. The two gauges share one independence group, as they do in `ghadi.service`.
Monotonicity was tested by adding a live, quiet channel from a brand-new independent
group to every state. The six dashboard presets were run through
`ghadi.service.process_window` under both rules.

## The only disagreement

| Seismic | Gauges | Fused score | Live groups | Groups that detected | Historical | Strict |
|---|---|---:|---:|---:|---|---|
| live, quiet | at least one detected | 0.81 | 2 | 1 | **WARNING** | ADVISORY |

The number 0.81 is the whole story. A detected gauge alone is 0.80, just at the WARNING
score threshold but held to ADVISORY for having one group. Adding a quiet channel at
0.05 lifts the noisy-OR to 0.81, which clears the score threshold by 0.01, and supplies
the second live group. Neither contribution is evidence of a surge.

## Scenarios

| Scenario | Fused score | Historical | Strict |
|---|---:|---|---|
| 2026 Bhote Koshi cascade | 0.92 | WARNING | WARNING |
| Regional earthquake with surge | 0.81 | WARNING | **ADVISORY** |
| Distant earthquake | 0.05 | no alert | no alert |
| Gauge unavailable | 0.05 | no alert | no alert |
| Background conditions | 0.10 | no alert | no alert |
| Increased processing latency | 0.92 | WARNING | WARNING |

## What each rule costs

* **Historical.** A single detecting source can reach WARNING whenever any other sensor
  is merely online. A false positive on one gauge becomes a top-tier alert, which is the
  failure the two-group requirement was written to prevent. It also makes the tier
  depend on which unrelated sensors happen to be powered, which is hard to defend after
  the fact.
* **Strict.** A real surge seen only by the gauge, with a working but quiet seismometer,
  is ADVISORY rather than WARNING. ADVISORY is still an alert ("prepare to move away from
  the river channel"), not silence. The case where this could matter most is a flood
  whose source the seismic station cannot hear, such as a small or distant failure.
  The 50:1 miss-to-false-alarm cost ratio in the configuration argues for caution here,
  and that is a judgement, not something this experiment can settle.

## A bug this experiment found

Four of the six dashboard presets omitted `station=on`, and the form treats an absent
checkbox as unchecked, so those scenarios silently ran with the seismic station
switched off. "Distant earthquake" therefore showed the station as unavailable because
it was off, not because the teleseism was set aside, and "Gauge unavailable" had no live
sensor at all. The presets are fixed, the scenario table above is from the corrected
run, and the README screenshots taken from the old presets are regenerated.

## What this does not change

* The operating points (0.60, 0.80, 0.05) are still assumed, not calibrated (n = 1).
* No false alarm rate changes: the measured rates are single-station seismic rates, and
  a single channel is held below WARNING under both rules.

## Recommendation

Adopt the strict rule. It removes the only case where a sensor reporting nothing raises
the alert level, it leaves every case where two sources detect untouched, and the price
is one downgrade from WARNING to ADVISORY that is still an alert. The choice of default
is the project owner's; the rule is implemented behind
`FusionConfig.warning_requires_supporting_groups` and currently defaults to the
historical behaviour.
