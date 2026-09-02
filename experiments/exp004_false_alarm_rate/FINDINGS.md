# Experiment 004 — What false-alarm rate does the detector actually run at?

**Question.** Everything before this measured whether the cascade *looks* different. That
is half a detector. The other half is how often something that is not a mass movement
gets through — and until now there was no denominator. The handoff's target is
**≤ 1 false alarm per station-month**.

**Answer: 12.9 per station-month, about 13× over target — and half of those turned out
to be distant earthquakes, not noise.** The corrected figure for genuine local noise is
roughly 6.5 per station-month, still ~6× over, and both numbers carry enormous
uncertainty because they rest on four events.

Run 2026-09-02. Noise corpus: 388 usable windows, **226.3 hours = 0.31 station-months**.

## The layers

| Layer | Windows | Per station-month |
|---|---:|---:|
| STA/LTA alone (the baseline every model must beat) | 120 / 388 | **387.3** |
| + signal-presence gate (issue 2.3) | 120 | 387.3 |
| + spectral criteria (the detector as constituted) | **4** | **12.9** |

**The spectral features do most of the work: a 30× reduction.** That is the strongest
evidence so far that they carry real information — exp003 and exp005 measured how much
the classes *overlap*, and this measures what the criteria actually reject.

**The signal-presence gate removes nothing.** Every window that produces an STA/LTA
trigger also passes the gate, which is unsurprising in hindsight: a trigger *is* a
transient, and the gate asks whether a transient exists. The gate remains useful for
what it was built for — stopping duration features scoring on windows with no event
(exp002) — but it should not be described as reducing false alarms, because it does not.

## Half the false alarms are teleseisms

The four surviving windows are not marginal. Two have LF/HF of **19.2** and **80.0**,
far beyond the cascade's 4.14, and all four occur at night local time. That pattern
prompted a check against the *global* catalogue, which the corpus's 6° exclusion radius
never considered:

| Window (UTC) | LF/HF | Centroid | Global earthquake with P arriving in-window |
|---|---:|---:|---|
| 2024-07-07 20:00 | 19.22 | 1.60 | **M6.2 Bonin Islands** (47°, P ~20:08) **and M5.5 Kamchatka** (60°, P ~20:24) |
| 2024-09-23 20:00 | 80.03 | 0.97 | **M6.0 Indonesia** (P ~20:00) |
| 2025-04-02 16:00 | 5.47 | 1.98 | M5.5 Alaska, P ~16:37 — just *outside* the window. Unexplained |
| 2025-04-23 16:00 | 8.01 | 1.56 | nothing plausible. Unexplained |

**Two of four are confirmed teleseisms, and they are the two most extreme.** This matters
in three separate ways:

1. **The corpus is mislabelled.** Those windows contain real earthquakes and are not
   noise. The exclusion catalogue must be extended globally — M ≥ 5.5 worldwide with
   travel-time-aware windows, not M ≥ 3.5 within 6°. That is a concrete fix to issue 1.3.
2. **But teleseisms are a real false-alarm source for GHADI, not merely a labelling
   artefact.** Attenuation strips high frequencies over thousands of kilometres, so a
   distant earthquake arrives looking low-frequency and long-duration — which is
   precisely the mass-movement signature the detector keys on. This is not bad luck; it
   is the same physics arriving by a different route, and no amount of tuning the
   spectral thresholds will separate them, because on these two features they are not
   separable.
3. **They are also the easiest false alarm to eliminate.** A global M ≥ 5.5 is catalogued
   within minutes and its arrival time at a known station is predictable to seconds. A
   production detector cross-checks the global catalogue and suppresses. **This should
   be an architectural component, not a filter bolted on later** — and it is cheap.

## The honest rate

| | Per station-month | 95% interval |
|---|---:|---|
| As measured (4 events) | 12.9 | ~3.5 – 33 |
| Excluding confirmed teleseisms (2 events) | ~6.5 | ~0.8 – 23 |

**Those intervals are the finding as much as the point estimates are.** Four events over
a third of a station-month cannot pin a rate; the data are consistent with anything from
comfortably-above-target to catastrophically-above-target. Quoting 12.9 without the
interval would be false precision, and quoting 6.5 as "the answer" would be worse,
because it is two events.

Reaching ≤ 1 per station-month needs roughly another 6–13× rejection. Two designed
mechanisms are not yet in play and are expected to supply exactly that:

- **Teleseism suppression** — removes half the observed rate, essentially for free.
- **Corroboration** — the architecture already requires an independent downstream gauge
  anomaly before a WARNING (rule 3, `ghadi.fusion`). An independent second channel is
  the intended multiplier. It cannot be measured yet: DHM gauge data is blocker B2.

## Earthquakes are counted separately, and should be

8 of 64 corpus earthquakes (12.5%) pass the same spectral criteria. These are not folded
into the per-station-month rate because they arrive at a different rate and constitute a
different failure — a real event misclassified, rather than a quiet period misread. At
roughly 75 regional M ≥ 4 events per year reaching this detector, that is ~9 additional
false alarms per year from regional earthquakes, on top of the noise rate.

## What this experiment cannot show

**Probability of detection is not estimable.** There is one positive example, and the
thresholds are that example's own feature values, so any POD figure would be 100% by
construction. **This is half an ROC.** A false-alarm rate against an unknown detection
rate cannot be called detector performance, and must never be quoted as if it were.

Further limits:

- **0.31 station-months** is thin for a per-station-month target, and the archive
  coverage map bounds how much more this station can supply.
- **The corpus under-samples August–December** (14–18 windows per month against 30–49
  for January–July), because those months exist in fewer years of the archive. The 2026
  cascade occurred in late August. Monsoon and post-monsoon noise — precisely when both
  mass movements and background noise peak — is the least well characterised part of
  this estimate.
- Triggering shows the expected diurnal shape (41% of windows at ~13:00 NPT against 25%
  at ~21:45 NPT), confirming cultural noise is present and that the hour stratification
  was worth doing.
