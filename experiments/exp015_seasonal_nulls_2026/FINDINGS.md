# Experiment 015: is the 2026 radar signal extreme against the same weeks in earlier years?

**Question.** exp014 ranked the 2026 three-track agreement patch first among clean
no-event windows, but only three such windows existed, so the rank could not go below
p = 0.25. Using the same late August weeks from 2022 to 2025, on the same tracks and
in both polarisations, is the 2026 patch still the largest?

**Answer.** Yes, on all three tracks. On two tracks, no.

| Polarisation | Tracks | 2026 patch | Nulls | Largest null | 2026 over largest | Rank p (floor) |
|---|---|---:|---:|---:|---:|---:|
| VV | 19, 85, 121 | **0.413 km2** | 13 | 0.040 km2 | **10.5x** | 0.071 (0.071) |
| VH | 19, 85, 121 | **0.115 km2** | 13 | 0.045 km2 | **2.6x** | 0.071 (0.071) |
| VV | 19, 85 | 0.063 km2 | 4 | 0.147 km2 | 0.43x | 0.40 (0.20) |
| VH | 19, 85 | 0.031 km2 | 4 | 0.189 km2 | 0.16x | 0.60 (0.20) |
| VV | 85, 121 | 0.085 km2 | 1 | 0.005 km2 | 18.8x | 0.50 (0.50) |
| VH | 85, 121 | 0.035 km2 | 1 | 0.021 km2 | 1.7x | 0.50 (0.50) |

* **The three-track result holds against a null four times larger.** The 2026 VV patch
  is 10 times the largest of 13 like-for-like windows from 2022 to 2026, and no null
  comes within a factor of 10. The rank floor fell from 0.25 (exp014) to 0.071, and
  2026 sits on it.
* **VV and VH agree on where.** Both largest patches sit 5.7 to 5.8 km from the
  catalogued source, about 0.1 km apart, as in exp014. The overlap between the VV and VH
  change maps is also higher in 2026 (Jaccard 0.095) than in any null window (0.005 to
  0.060).
* **VH is weaker.** 2.6 times its largest null is a clear lead, but not the margin VV
  shows.
* **Two tracks are not enough.** On tracks 19 and 85 alone, a null window ending
  2 to 6 September 2023 has a larger patch than 2026 in both polarisations. The
  radar confirmation of 2026 depends on all three tracks agreeing.

Run 2026-09-17 against the Microsoft Planetary Computer catalogue. Regions are cached,
so later runs are offline.

## Design

`ghadi.eo_null.seasonal_window_sets` searched each year from 2022 to 2026 around
26 August. For each track it built the window straddling that date (lag 0) and up to
three earlier cycles, all with 11 to 13 day gaps between before and after images. The
2026 lag 0 window is the event, and the other 19 windows are nulls. Region (8 km half
width around 28.255 N, 85.520 E), thresholds, and tracks are those of exp012 to exp014.
Nothing was tuned after exp014.

Track coverage decides which nulls are comparable. 13 nulls have all three tracks. 2023
had only tracks 19 and 85 at lags 0 to 2, and a few lag 3 windows lost a track, so those
nulls are compared with the 2026 event computed on the same two tracks.

## The recurring patch near the river

The 2023 lag 0 null patch (VV 0.147 km2, VH 0.189 km2) sits at 28.272 N, 85.534 E,
about 2.2 km from the catalogued source. A weaker patch appears at almost the same spot
in the 2022 lag 1 window (VH 0.045 km2 at 28.270 N, 85.531 E), the largest VH null on
three tracks. A spot that changes in late August of two different years is more likely a
seasonal surface, such as monsoon water or wet sediment on the valley floor, than a slope
failure. It could also be a real small event in September 2023. This was not checked
against optical imagery or catalogues, so it is recorded here and not interpreted
further.

The 2023 window had no track 121 image, so it cannot say whether this spot would pass a
three-track test. In 2022, where all three tracks exist, the same spot stayed at 0.045 km2
or less.

## What this does not show

* **p = 0.071 is still the floor.** With 13 nulls, no result can rank lower. It is
  not below 0.05, and the number of nulls, not the size of the signal, is what limits it.
* **The nulls are not independent.** Adjacent lags share images, and all come from one
  region. The effective number of nulls is smaller than 13.
* **One region, one event.** A clean result here says nothing about how often the test
  would miss or falsely confirm elsewhere.
