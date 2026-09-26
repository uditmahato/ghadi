# Experiment 012: can radar imagery confirm the 2026 source, and find the other events?

**Question.** The positive class is one event (n = 1). Seismic detection gives the WHEN;
it cannot by itself prove WHERE the ground failed. Free Sentinel-1 radar sees through
monsoon cloud and revisits every 12 days per track. Does a before/after comparison show
a changed patch at the catalogued 2026 source zone, and does the same method find the
other catalogue candidates whose times and places are known only from news reports?

**Answer.** Yes for 2026, and independently of the seismic record: on two of the three
satellite tracks that cover the source zone the event pair's largest changed patch is
3.3 and 4.0 times larger than its own pre-event control on the same track, above a 2.0
floor fixed before the pairs were inspected; the third track sits just under, at 1.85.
All three tracks place their largest patch in one cluster about 3 km across, 4 to 6 km
north of the catalogued point and inside its 8 km uncertainty. **No other catalogue event
is cleanly confirmed.** Thame 2024 and Langtang 2015 each show one track marginally above
background with a second track agreeing on location; those are leads, not labels. Spring
snowmelt and peak monsoon produce so much natural change that Melamchi 2021 and
Rasuwagadhi 2025 are lost in it. **The positive class stays n = 1.**

Run 2026-09-10, Sentinel-1 RTC, VV polarisation, 10 m pixels, via the Microsoft
Planetary Computer. Two passes were made: the first exposed two pairing faults (below),
which were fixed in code before the final run that produced `results.json`.

## Design, briefly

For each event: search scenes from 40 days before to 30 days after the origin; keep one
frame per satellite pass (the frame that best covers the region); form same-track pairs
(last pass before the origin, first pass after, same relative orbit and pass direction);
read only the region of interest; compute the backscatter log ratio in dB, median filter
it over 3 pixels, flag pixels beyond 3 dB either way, and size the connected patches.
For every event pair, run a **control pair** on the same track from the cycle before,
and judge the event against it: above background only if its largest patch is at least
2.0 times the control's. Region half width is the larger of 5 km and the catalogued
location uncertainty. Threshold and ratio are configuration (`ghadi.config.EoConfig`),
not tuned per event.

## The 2026 result

| Track | Before to after | Event patch (km2) | Control patch (km2) | Ratio | Distance from catalogued source | Against control |
|---|---|---:|---:|---:|---:|---|
| 19 (descending) | 24 Aug to 5 Sep | 0.641 | 0.159 | 4.0x | 3.8 km | **above background** |
| 85 (ascending) | 16 Aug to 28 Aug | 0.828 | 0.255 | 3.3x | 5.6 km | **above background** |
| 121 (descending) | 19 Aug to 31 Aug | 0.364 | 0.197 | 1.85x | 3.7 km | within background (just under 2.0x) |

Every region was fully usable (valid fraction 1.0). The controls are the smallest of any
event in this experiment (0.16 to 0.26 km2): late August at this site, after the worst
of the monsoon, is a quiet season for radar change, which is what makes the excess
readable at all.

### The three tracks agree on where

| Tracks | Largest patches apart |
|---|---:|
| 19 and 121 | 0.96 km |
| 85 and 121 | 2.29 km |
| 19 and 85 | 3.07 km |

Three viewing geometries, acquired on different days, each independently pick a largest
patch inside the same roughly 3 km cluster centred near 28.29 N, 85.52 E. That is much
stronger than three patches anywhere in a 16 km box, and it is why track 121, whose
ratio is just under the floor, still supports the result: its patch is 0.96 km from
track 19's. The cluster lies 4 to 6 km north of the catalogued point (28.255 N,
85.520 E), which carries 8 km of uncertainty. Read carefully, the imagery suggests the
failure zone sits a few kilometres north of where the catalogue puts it. That is a
refinement to test against ground truth, not a ground truth in itself.

## The other candidates

| Event | Region half width | Tracks | Best track (ratio) | Location agreement | Outcome |
|---|---:|---|---|---|---|
| Jure, Aug 2014 | | none | | | no scene: predates the Sentinel-1 archive (Oct 2014) |
| Langtang, Apr 2015 | 5 km | 3 | orbit 19, 5.44 vs 2.46 km2 (2.2x) | tracks 19 and 121 patches 1.6 km apart | one marginal track; orbit 121 **inconclusive** (only 17% of the region covered by early Sentinel-1A frames); orbit 85 buried by a 12.8 km2 snowmelt control |
| Melamchi, Jun 2021 | 15 km | 3 | none (0.07x to 0.33x) | patches 5 to 12 km apart | not confirmed; controls 4.2 to 12.7 km2 in peak monsoon over a very large region |
| Thame, Aug 2024 | 6 km | 3 | orbit 12, 0.671 vs 0.300 km2 (2.2x) | tracks 85 and 12 patches **0.29 km apart**, 5.7 km from the catalogued point | one marginal track, and a second track (1.86x, just under) pointing at the same spot: the best lead in the set |
| Rasuwagadhi, Jul 2025 | 12 km | 3 | none (0.05x to 1.35x) | patches 11 to 17 km apart | not confirmed; peak monsoon, small linear event |

A patch that is not larger than its control is not a detection, however tempting the
distance to the source makes it look. Rasuwagadhi's orbit 85 patch is 1.7 km from the
catalogued point and is still smaller than the control's.

## Why controls are indispensable

Every single pair in this experiment, event or control, in every season, returned
"change detected" at the raw threshold, with thousands to a hundred thousand small
patches per region. Raw radar change alone confirms nothing in the Himalaya. What
separates 2026 from noise is the ratio to a control on the same ground and the same
track, and the fact that the ratio floor was fixed before the pairs were seen.

Season sets the sensitivity. The controls measure the natural 12-day change:

| Event and month | Control patches (km2) |
|---|---|
| Langtang, April (snowmelt) | 2.5, 12.8 |
| Melamchi, June (monsoon onset) | 4.2, 8.8, 12.7 |
| Rasuwagadhi, July (peak monsoon) | 0.1, 1.0, 7.6 |
| Thame, August | 0.06, 0.13, 0.30 |
| Bhote Koshi 2026, late August | 0.16, 0.20, 0.26 |

The method is weakest in exactly the seasons when most of these events happen. A
negative result in snowmelt or peak monsoon means "not separable from the background",
not "did not happen".

## What the first run taught, now enforced in code

1. **Two frames of one pass are not a pair.** A satellite pass is delivered as several
   frames sharing a date and track. The first run built a Thame "control" from two
   frames of the same 7 August pass, which are near-identical over their overlap and
   would show almost no change, and it also chose a frame covering a quarter of the
   region, which failed on a shape mismatch. `ghadi.eo_fetch` now keeps one frame per
   pass (the best covering one) and takes controls only from the previous cycle
   (`previous_pass`), with tests in `tests/test_eo_passes.py`.
2. **A raw threshold is not a verdict.** `compare_to_control` was added after the first
   run showed controls as large as events. The raw per-pair verdict is untouched and
   the comparison is recorded separately per pair.
3. **Missing view is not missing change.** Langtang orbit 121 could not be judged
   because early 2015 frames covered 17% of the region. It is reported as inconclusive,
   never as "no change".

## What this does not change

- **n = 1 stands.** This confirms the one event we have; it does not manufacture new
  labelled windows. Thame and Langtang are leads for a closer look, not positives.
- **No lead time.** Imagery bounds the event to the 12 days between passes. The minute
  comes from the seismic onset, and nothing here touches the warning path.
- **VV only, 10 m, 3 dB, one polarisation, one sensor.** Small or linear events (a
  debris flow along a channel) may fall below the 0.02 km2 patch floor or fragment.
- **"Largest patch anywhere in the region" is a coarse statistic.** It can be a river
  reach or a glacier tongue. Spatial agreement across tracks is what rescues it here.
- The location refinement for 2026 has not been checked against any field report.

## Follow-ups

- Test the excess at the expected location rather than anywhere in the region.
- Add VH polarisation and, when a clear scene exists, optical NDVI change (every optical
  scene around 26 August 2026 was 60 to 99% cloud).
- For snowmelt and monsoon events, build the control from the same dates in earlier
  years instead of the previous cycle, so the seasonal background is matched.
- Take the Thame lead further with a tighter region and a longer control series.
