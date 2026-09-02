# Experiment 003 — Does the spectral separation survive a real earthquake corpus?

**Question.** exp001 and exp002 compared the 26 August 2026 cascade against *two*
hand-picked earthquakes and found the spectral features separated cleanly. Both said
in terms that four windows cannot establish separability. Issue 1.2 has now harvested
64 real earthquakes on the same station and pipeline. Does the separation hold?

**Answer: not cleanly. Between 12% and 20% of real earthquakes look at least as
mass-movement-like as the cascade does.** The separation is real but it is a tendency,
not a boundary — and every previous statement in this repository about "clean"
separation was an artefact of comparing against two events.

Run 2026-09-02. Corpus: `data/corpus/earthquakes.json`, `NK.KKN..BHZ`.

## The headline numbers

Earthquake population, n = 64:

| Feature | median | p10 | p90 | extreme |
|---|---:|---:|---:|---:|
| LF/HF ratio | 1.48 | 0.38 | 6.71 | max **35.63** |
| Spectral centroid (Hz) | 3.11 | 1.90 | 4.93 | min **0.98** |

The cascade sits at LF/HF **4.14**, centroid **2.04 Hz** — inside both distributions:

| Criterion, set exactly at the cascade's own value | Earthquakes meeting it |
|---|---|
| LF/HF at or above 4.14 | **13 / 64 (20%)** |
| Centroid at or below 2.04 Hz | **8 / 64 (12%)** |
| **Both simultaneously** | **8 / 64 (12.5%)** |

A threshold placed exactly at the cascade's value is the most permissive one available,
because it is fitted to the single event we are trying to detect and allows no margin.
**These fractions are therefore a lower bound on the false-alarm rate any real operating
point would incur**, not an estimate of it.

## The confounds, checked rather than assumed

| Relationship | Rank correlation |
|---|---:|
| LF/HF vs epicentral distance | +0.04 |
| Centroid vs distance | +0.03 |
| LF/HF vs magnitude | **+0.44** |
| Centroid vs magnitude | **−0.42** |

**Distance does not drive the spectral features in this corpus.** That was not the
expected result — attenuation preferentially strips high frequencies with distance — and
it is worth revisiting on a corpus with better near-field coverage, since only 4 of 64
events lie within 150 km while the cascade was at 55.9 km.

**Magnitude does.** Larger earthquakes are systematically more low-frequency on both
features, which is physically unsurprising: a bigger rupture has a longer source
duration and a lower corner frequency. This matters for M3 far more than distance does.
**A classifier trained on these features without controlling for size may learn a
size detector rather than a mass-movement detector** — and would then fire on any large
earthquake and miss any small cascade, which is close to the opposite of what GHADI is
for.

## The comparison that is actually fair

The cascade's signal was catalogued by USGS as M4.4 before being identified as
landslide-generated. Comparing it against earthquakes of similar size and distance:

| Comparison group | n | Meeting both criteria |
|---|---:|---:|
| All earthquakes | 64 | 8 (12.5%) |
| Magnitude-matched, M4.0–4.6 | 48 | 4 (8%) |
| **Magnitude- and distance-matched, M4.0–4.6 and < 250 km** | 25 | **1 (4%)** |

Against earthquakes of comparable size and range — the population a real detector in
this corridor would actually be confused by — the cascade is distinctive: one earthquake
in twenty-five looks like it on both features simultaneously.

**This is the encouraging half of the result, and it should not be over-read.** n = 25,
one confusable event, and a threshold with no margin. The honest summary is that the
discriminant is real, weaker than two events suggested, and not yet characterised well
enough to set an operating point.

## What this means for the project

**The core hypothesis is not falsified, but the clean-separation claim is retired.**
GHADI's premise (RQ1) is that mass movements can be discriminated from earthquakes at a
usable false-alarm rate on a sparse network. At corpus scale, single-feature
thresholding does not achieve that. What remains open, and is now testable, is whether a
*trained, calibrated, multi-feature* classifier does — which is M3's question, and it
now has a corpus to answer it on rather than four windows.

**Order-of-magnitude context for the false-alarm rate.** The catalogue returned 150
events at M≥4.0 within 4° over roughly two years, so ~75/year reach this detector's
input. At the magnitude- and distance-matched rate of 4%, earthquakes alone would
produce roughly 3 false alarms per year before any corroboration requirement is applied.
Against the handoff's target of ≤1 per station-month, that is not immediately
disqualifying — but earthquakes are only one false-alarm source, and the noise corpus
(issue 1.3) has not yet been measured.

**Two features, and they are correlated.** Both encode the same physics from different
angles, and exp002 removed `emergence_s` from contention. GHADI currently rests on one
physical idea expressed twice. Issue 2.5's three-component features (polarisation, H/V
ratio) would add a genuinely independent axis, and on this evidence that work is more
urgent than it appeared.

## Two findings about the data itself

**NK.KKN has no archived waveforms for 86 of 150 catalogue events, and the gap is not
random.** 84 of the 86 fall in 2025, and **47 of them on 2025-01-07 alone** — the day of
the M7.1 Tibet earthquake, whose entire aftershock sequence is missing, the M7.1
included. Whether this is a station outage, a telemetry loss, or an archive gap cannot
be determined from outside.

The operational implication does not depend on which it was: **Nepal's one open
broadband station may be unavailable precisely when a large regional event occurs.**
That is risk R4 (single-station fragility) with a date attached, and it is a concrete
question for the DMG/NEMRC letter (blocker B3).

**Onset picking by causality was not an edge case.** 32 pre-origin triggers were
rejected across 21 of the 64 usable windows — **a third of the corpus**. Under a
first-trigger rule, a third of these labelled earthquakes would have had their features
computed from an unrelated earlier transient. exp002 found this on one window; it is
systematic.

## What this experiment cannot show

- It compares the cascade against earthquakes only. The noise corpus (issue 1.3) is
  written but not yet run, so the dominant false-alarm source is unmeasured.
- **n = 1 on the positive side.** Every statement here is about how one mass movement
  compares to 64 earthquakes. The cascade's own values carry no error bars, and a
  second cascade could sit anywhere. This is R1 (too few labelled positives) in its
  most concrete form and no amount of earthquake harvesting fixes it.
- Single-feature thresholds are not a classifier. A model combining features may
  separate materially better, and that is the point of M3.
- The corpus is one station, one channel (BHZ), and vertical-component only.
