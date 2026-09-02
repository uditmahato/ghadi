# Experiment 002 — Does the M2 feature rework survive contact with real data?

**Question.** exp001 found the temporal features broken. M2 redefined `emergence_s`
relative to the trigger onset (issue 2.1), gated the duration features on signal
presence (issue 2.3), and added instrument-response deconvolution (issue 2.4). Do the
repaired features order the four exp001 cases correctly on real waveforms?

**Answer: two of the three repairs work. `emergence_s` does not, and should not enter
a classifier on this evidence.**

Run 2026-09-02, same four windows as exp001, `NK.KKN..BHZ`.

## Results (ground velocity; counts differ only in units)

| Case | Class | signal? | onset s | **emergence s** | dur. ratio | LF/HF | centroid Hz | broken emergence |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 26 Aug 2026 Bhote Koshi | mass movement | yes | 620.3 | **28.3** | 0.513 | **4.14** | **2.04** | 28.3 |
| Reference EQ M4.3, 18 Aug | earthquake | yes | 324.3 | **3.9** | 0.227 | 0.39 | 5.78 | 287.9 |
| Reference EQ M4.5, 19 Jul | earthquake | yes | 642.0 | **36.6** | 0.090 | 0.76 | 3.94 | 36.6 |
| Quiet noise (T−7d) | noise | **no** | — | **NaN** | **NaN** | 0.68 | 5.48 | 387.1 |

## What works

**Issue 2.3 — the signal-presence gate works, and it fixes exp001's headline failure.**
The noise window is correctly identified as containing no event, so `emergence_s` and
`duration_ratio` return NaN instead of numbers. The deprecated feature in the last
column still reports 387.1 s for that same window, which is the exp001 pathology
preserved for comparison: a window with no event was being handed the largest temporal
"score" of any case. That is precisely why the composite ranked noise above the target.

**Issues 2.1 and 2.3 are one issue, not two.** Measuring from the onset is not
sufficient by itself. On a window containing no event, 10% of the peak is crossed at
the first sample and 90% wherever the largest random fluctuation lands, so noise scored
52.8 s against 20.3 s for a genuine emergent arrival on the test fixtures — still the
wrong ordering. Emergence is therefore gated on signal presence too.

**Issue 2.4 — response deconvolution works and is a no-op on discrimination.** LF/HF is
identical in counts and in velocity (4.14 both), the centroid moves by <0.1 Hz. This is
the expected and desired result: the units become physical and cross-station comparable
without the physics changing. Features are no longer confined to a single station.

**The spectral features remain the load-bearing ones.** Both orderings hold, in both
unit systems, unchanged from exp001.

## What does not work: `emergence_s`

Bounding the forward search (`emergence_search_s = 120 s`) fixed one earthquake and not
the other. The M4.3 case fell from 287.9 s to 3.9 s. The M4.5 case still reads **36.6 s
— larger than the cascade's 28.3 s**, which is the wrong direction for the feature's
entire physical premise.

Direct inspection of both windows explains why, and neither reason is fixable by
tuning:

**M4.5 — the peak is the S wave, so "rise time" measures propagation, not the source.**
Origin is at t = 600 s, the trigger fires at 642 s (a plausible P arrival at this
distance), and the envelope then jumps from ~3,000 to ~17,000 between 30 and 40 s after
onset, peaking at 37.6 s. That is S following P. The feature is supposed to measure how
slowly a source ramps up; on a regional earthquake it measures the S−P interval
instead, and S−P grows with distance. **`emergence_s` conflates a source property with
a propagation property.**

**M4.3 — the window does not contain the event it is labelled with, at least not
first.** The first trigger fires at 324.3 s, which is *before* the catalogued origin
time at 600 s. It is an unrelated earlier transient; the earthquake itself is the third
of four triggers, at 615.8 s. The 3.9 s emergence is a correct measurement of the wrong
arrival.

That second point is a **data-quality finding that reaches beyond this feature**. A
window cut around a catalogue origin time may contain other events, and "first trigger"
is not a safe way to locate the labelled one. Issue 1.2 harvests ≥100 reference
earthquakes this way; unless onset picking is made robust, some fraction of that corpus
will be labelled for one event and measured on another.

## Recommendation

**Do not include `emergence_s` in the M3 classifier.** On the present evidence it does
not separate the classes, and it is contaminated by distance.

**Do not tune `emergence_search_s` until it does.** Two earthquakes — one of which is
not even the intended event — cannot distinguish "the bound needs adjusting" from "the
feature conflates source ramp with S−P time". Tuning a parameter until two test cases
come out right is the failure mode the split policy exists to prevent, and it would
produce a number that looks good here and generalises to nothing.

What would settle it, in M1/M2 order:

1. Robust onset picking that selects the arrival matching the catalogue origin time
   rather than the first trigger in the window (affects issue 1.2's corpus as well).
2. Distance-corrected evaluation — bin earthquakes by epicentral distance and check
   whether emergence still tracks S−P once that is controlled for.
3. Then issue 2.6's bootstrap separation, over the real corpus, with the split
   frequency and every threshold published alongside.

Until then the honest position is that GHADI's discrimination rests on two correlated
spectral features, which is exactly the fragility exp001 warned about, and M1's corpus
is the thing that unblocks it.

## What this experiment cannot show

Four windows, one per class, cannot establish separability at any false-alarm rate.
This checks that the repaired features are not broken in the specific ways exp001
documented. It found that one of them still is.
