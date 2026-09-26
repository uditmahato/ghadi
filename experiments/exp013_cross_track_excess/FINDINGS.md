# Experiment 013: do independent radar tracks agree on WHERE the ground changed?

**Question.** exp012 confirmed the 2026 source with a coarse statistic: the largest
changed patch anywhere in a 16 km box, judged against a same-track control. Its stated
weakness is that the largest patch can be a river reach or a glacier tongue. Does the
excess sit in the same pixels on all three viewing geometries, and is that agreement
larger than the same test gives for a window with no event in it?

**Answer.** Yes for 2026, and clearly. A connected patch of **0.41 km2** where at least
two of the three tracks see change in the event window and not in their own pre-event
controls, against **0.075 km2** for the same test run on the weeks before the event on
the same ground: **5.5 times larger**. Where all three tracks agree the area is 0.53 km2
against 0.08 km2 (6.6 times). The patch is centred at 28.305 N, 85.503 E, 5.8 km from
the catalogued point and 0.2 km from one of the three patches exp012 found, inside the
same northern cluster. The null patch lies elsewhere, 1.8 km from the catalogued point.
No older event passes this test. Thame 2024 comes closest at 2.4 times on a 0.05 km2
patch, at the same spot exp012 flagged. Langtang, Melamchi, and Rasuwagadhi fall below
their nulls. **The positive class stays n = 1.**

Run 2026-09-14, fully offline from exp012's cached regions, with the network forbidden.

## Design

For each event and each track: the per-pixel radar change mask for the event pair and
for the pre-event control pair, using the same 3 dB rule and 3 pixel median filter as
exp012. A track's *excess* is a pixel changed in the event pair and not in its control.
Summing excess over tracks gives, per pixel, how many independent viewing geometries
saw new change there. The statistic is the largest connected patch where at least two
agree. The **null** swaps the roles on the same data: pixels changed only in the
pre-event window. Regions from different scenes are cropped to their common pixel grid
first (`ghadi.eo_fetch.align_arrays`); for every event here the grids matched exactly,
so no resampling was involved.

## The 2026 result

| Window | Largest patch, 2 or more tracks | Area, 2 or more tracks | Area, all 3 tracks | Patch centre | From catalogued point |
|---|---:|---:|---:|---|---:|
| Event (changed only after the event) | **0.413 km2** | 4.56 km2 | 0.534 km2 | 28.3048 N, 85.5030 E | 5.8 km |
| Null (changed only before the event) | 0.075 km2 | 2.63 km2 | 0.081 km2 | 28.2586 N, 85.5021 E | 1.8 km |
| Ratio | **5.5** | 1.7 | 6.6 | | |

The per-track raw change is the same in both windows: 19.7, 19.7, and 20.1 km2 in the
event pairs against 20.4, 18.3, and 17.2 km2 in the controls. On any single track the
event is invisible in the total. It appears only where independent geometries agree on
the same pixels, net of their own background, which is exactly what a real change on
the ground should do and what speckle, viewing geometry, and a shifting river should
not.

The event patch sits 0.21 km from exp012's orbit 85 patch (28.3034 N, 85.5044 E) and
2.5 to 3.3 km from the other two, so the pixel-level test lands inside the cluster the
coarse test found, 4 to 6 km north of the catalogued point. Two different statistics,
one place.

## The other candidates

| Event | Tracks | Event patch (km2) | Null patch (km2) | Ratio | Event patch from catalogued point | Reading |
|---|---:|---:|---:|---:|---:|---|
| Langtang, Apr 2015 | 3 | 0.030 | 0.067 | 0.45 | 4.9 km | below null; snowmelt change everywhere, agreeing nowhere in particular |
| Melamchi, Jun 2021 | 3 | 0.045 | 0.880 | 0.05 | 10.6 km | below null; monsoon null of 63 km2 at two-track agreement |
| Thame, Aug 2024 | 3 | 0.051 | 0.021 | **2.4** | 5.7 km | modest lead, at the spot exp012 flagged (27.858 N, 86.563 E) |
| Rasuwagadhi, Jul 2025 | 3 | 0.027 | 0.180 | 0.15 | 6.5 km | below null; peak monsoon |
| Jure, Aug 2014 | 0 | | | | | no scene, predates the archive |

Thame is consistent across both experiments: two tracks agreed to 0.3 km in exp012, and
the pixel-level patch is at the same place here, above its null. It is still a 0.05 km2
patch in a small event, so it stays a lead for a tighter, longer-baseline look (#29).

For Langtang, track 121 covers only 17% of the region (early Sentinel-1A frames), so the
agreement test there is effectively two tracks over most of the ground. It is reported
as it is, not padded.

## What this changes

- exp012's coarse "largest patch anywhere" statistic is replaced by a localized one:
  pixel-level agreement across independent tracks, each net of its own control, judged
  against the same test on a pre-event window. It is offline, needs no network, and is
  the standard for any future candidate.
- The 2026 confirmation is now spatial as well as quantitative: three geometries, two
  statistics, one place.

## What this does not change

- **n = 1.** Thame is a lead, not a label.
- **No lead time.** Nothing here touches the warning path.
- **Same limits as exp012.** VV only, 10 m, 3 dB, one sensor; small or linear events can
  fall below the patch floor; the location refinement is untested against the ground.
- The null uses one pre-event cycle per track. A longer control series would give a
  distribution rather than a single point, which is the follow-up for Thame.
