# Experiment 016: does the Thame 2024 radar lead survive a proper null test?

**Question.** Thame (16 Aug 2024, a glacial lake outburst) was the only older catalogue
event that looked promising from orbit. In exp012 two tracks put their largest patch
within 0.3 km of each other, and in exp013 its cross-track patch was 2.4 times its
single null. Does it rank above like-for-like windows with no event, the way 2026 did in
exp015?

**Answer.** No. Thame is not confirmed from orbit, and the spot that made it look
promising is a place that changes in ordinary years too.

| Polarisation | Tracks | Thame patch | Nulls | Largest null | Thame over largest | Rank p (floor) |
|---|---|---:|---:|---:|---:|---:|
| VV | 12, 85, 121 | 0.051 km2 | 8 | 0.115 km2 | 0.44x | 0.22 (0.11) |
| VH | 12, 85, 121 | 0.026 km2 | 8 | 0.114 km2 | 0.23x | 0.22 (0.11) |
| VV | 12, 85 | 0.032 km2 | 4 | 0.016 km2 | 2.0x | 0.20 (0.20) |
| VH | 12, 85 | 0.020 km2 | 4 | 0.005 km2 | 4.3x | 0.20 (0.20) |
| VV | 85, 121 | 0.014 km2 | 3 | 0.004 km2 | 3.6x | 0.25 (0.25) |
| VH | 85, 121 | 0.003 km2 | 3 | 0.003 km2 | 1.1x | 0.25 (0.25) |

* **On all three tracks Thame ranks second of nine in both polarisations.** A window
  ending 25 July to 1 August 2022 has a patch more than twice as large in VV and four
  times as large in VH. A 2021 window (VV 0.049 km2) is almost level with Thame.
* **On two tracks Thame ranks first, but at the floor.** With only three or four nulls
  the best possible rank is 0.20 or 0.25, which cannot separate an event from chance.
  2026 also led on some two-track sets without being distinguishable there (exp015).
* **The flagged spot is not special.** Thame's three-track patch sits 0.3 km (VV) and
  0.7 km (VH) from the spot exp012 flagged. But in 7 of the 30 null comparisons the
  largest patch also falls within 0.7 km of that spot, in 2021, 2022, and the weeks
  before Thame in 2024. Something there changes often, so two tracks agreeing on it in
  2024 was not evidence of the outburst.

Run 2026-09-17 against the Microsoft Planetary Computer catalogue. Regions are cached,
so later runs are offline.

## Design

Identical to exp015, pointed at Thame. The region is centred on the catalogued point
(27.870 N, 86.620 E) with the catalogued 6 km uncertainty as its half width, the same
region exp012 and exp013 used. It was deliberately not recentred on the flagged spot,
because choosing a region from the data and then testing inside it would be circular.
The flagged spot is only reported. Nulls are the three earlier cycles of 2024 and the
same weeks of 2021 to 2023, with the same cadence rules and thresholds. Nothing was tuned
for Thame.

Track 12 was missing from the earlier 2024 cycles and track 121 from all of 2023, so 8
of the 15 nulls have all three tracks. The rest are compared with Thame on the same two
tracks.

## A wrong expectation, recorded

Before the run, `run.py` stated that 2021 would give no nulls, because two satellites
were flying on a 6 day repeat. That was wrong. Each satellite still repeats every 12
days on its own, and the cadence rule picks those 12 day pairs and skips the 6 day ones.
2021 gave four clean three-track nulls, one of which nearly matches Thame. The design
note in `run.py` is left as written so the record shows what was expected.

## The largest null

The 2022 window ending 25 July to 1 August is peak monsoon. It has the most changed area
of any Thame window (VV 5.5 km2, VH 5.4 km2 where at least two tracks agree), and its VV
and VH largest patches sit about 12.5 km apart, at opposite sides of the region. That looks
like widespread wet season change, not one slope failure. It is still a fair null: it is
the kind of change the test must rise above, and Thame does not.

## What this means

* **The positive class stays at one event.** No older catalogue event is confirmed by
  radar, and Thame was the best candidate.
* **This is not evidence that Thame did not happen.** A glacial lake outburst mostly
  moves water and sediment along an existing channel, which may change radar backscatter
  much less than the 2026 slope collapse. The test here was built around 2026 and may
  simply not see this kind of event.
* **A place that agrees across tracks must also be checked across years.** exp015 found
  the same problem near the 2026 river, and here it decided the result.
