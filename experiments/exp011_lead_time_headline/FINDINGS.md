# Experiment 011 — Minutes of warning at Timure, Syabrubesi, Bidur

**Question.** If GHADI had detected the 26 August 2026 initiation and fired an alert,
how many minutes of warning would each downstream settlement have received, and how
sensitive is that to the pipeline latency?

**Answer: at any realistic pipeline latency, Bidur gets ~36–37 minutes and Syabrubesi
~9–10; Timure gets 2–3 minutes and is not saved by a faster pipeline, because its
margin is set by its distance from the source, not by detection speed.**

Run offline; this is a lookup-and-subtract on the single calibrated travel record, not
a new measurement. Positive class n = 1.

## The headline table

Minutes of warning = surge arrival (`ghadi.travel`: 4 / 11 / 38 min, calibrated on the
one event) minus warning latency (everything from initiation to an issued alert).

| Pipeline latency | Timure | Syabrubesi | Bidur |
|---|---:|---:|---:|
| 30 s (optimistic) | 3.5 | 10.5 | 37.5 |
| 60 s (configured budget) | 3.0 | 10.0 | 37.0 |
| 120 s (re-scope threshold, B4) | 2.0 | 9.0 | 36.0 |
| ~20 min (what happened in 2026) | **−16** | **−9** | 18 |

## What the numbers say, and what they do not

**The pipeline latency barely moves the answer.** Across the whole plausible range
(30–120 s) every settlement's warning changes by about one minute. The lead time is
dominated by how far the water has to travel, not by how fast we detect — so shaving
seconds off detection is not where the warning comes from. This is the opposite of the
usual real-time-systems intuition and worth stating plainly.

**Bidur is the winnable case, and reality confirms it.** At a 20-minute alert — roughly
what actually happened — the model still leaves Bidur 18 minutes. Bidur *did* evacuate a
school of 1,643 on ~14 minutes of informal notice. The one real-world data point we have
lands inside the model's figure, which is the only external check n = 1 permits.

**Timure is not a latency problem.** At ~4 minutes' surge arrival it sits below the
10-minute actionable floor (the Bidur-precedent judgement, not a measured threshold) in
*every* scenario, including the 30-second one. No achievable pipeline changes that. The
honest consequence: for settlements this close to a transboundary source, seismic
detection alone cannot deliver an evacuation-scale warning, and the value there is
seconds of automatic siren and a "move to high ground" reflex, not an orderly
evacuation. Saying
otherwise would oversell the system to exactly the people closest to the hazard.

## Caveats carried from ghadi.travel

- **n = 1.** Every minute here rests on one event. The arrival times are observed
  anchors, not a hydraulic model; the ±3 min band in the record is initiation-time
  uncertainty only and is not a confidence interval.
- **The actionable floor (10 min) is a judgement**, anchored only on the Bidur
  precedent. It flags; it does not gate.
- **Negative lead times are reported, not clamped** — the −16 min for Timure at a
  20-minute alert is the point, not a bug to hide.

## What this establishes for the project

The system's headline claim is now a number with provenance, and it travels end-to-end:
`results.json` includes the sample CAP for the 60 s budget, whose `<description>` states
"~37 minutes of warning" at Bidur and whose `ghadi:travel_note` parameter carries the
n = 1 caveat into the machine-readable message. The lead time is no longer an assertion
in a slide; it is emitted by the code, with its limits attached.
