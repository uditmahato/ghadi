# Experiment 014: is the 2026 radar signal extreme against many no-event windows?

**Question.** exp013 found a 0.41 km2 patch where at least two of three Sentinel-1 tracks
agree on new change after 26 Aug 2026, 5.5x its null. That null was a single point, and
every radar result so far used one polarisation (VV). Does the event hold up against a
distribution of earlier no-event windows, and does the second polarisation (VH) see it
independently, in the same place?

**Answer.** Partly, and the "partly" matters.

* **With all three tracks, yes, in both polarisations.** Against every clean three-track
  null window available (three of them, late July to mid August), the event's largest
  agreement patch is the biggest: 14.9x the largest null in VV (0.413 against 0.028 km2)
  and 4.5x in VH (0.115 against 0.026 km2).
* **VV and VH put it in the same place.** The two polarisations are processed
  independently, and their three-track event patches sit **0.11 km apart**, 5.7 to 5.8 km
  from the catalogued point and 0.2 km from exp012's orbit 85 patch. Their overall
  agreement maps overlap 6x more in the event window than in the three-track nulls
  (Jaccard 0.095 against a mean of 0.016).
* **But the evidence is thin, and it depends on three geometries.** With only three clean
  three-track nulls, the best possible empirical rank is p = 0.25, and that is what the
  event gets: first of four, not significant. On the two tracks that have a longer clean
  history (orbits 85 and 121), the event does **not** stand out: its patch sits inside
  the spread of four May and June nulls (VV p = 0.6, VH p = 0.8), and the two-track VV/VH
  overlap is no higher than in those nulls.

So exp013's 5.5x holds up against more than one no-event window, and a second
polarisation independently locates it. It is not a statistically established detection,
and it needs all three viewing geometries. **The positive class stays n = 1.**

Run 2026-09-17, Sentinel-1 RTC, VV and VH, 10 m pixels, via the Microsoft Planetary
Computer. 41 passes found, 32 regions per polarisation, no read failures.

## Design

One search from 170 days before to 14 days after the origin, over the same 16 km box as
exp012 and exp013. `ghadi.eo_fetch.cycle_windows` builds, per track, the event window
(lag 0) and the same test moved back one acquisition cycle at a time. Every window gap
must be 11 to 13 days: a missing pass stops the sequence, and a 7 day window (a second
satellite sharing the track in June and July) is skipped, because a shorter window has
less time for natural change and would make a softer null. Each window gets exp013's
`cross_track_excess` statistic: per track, pixels changed in the window and not in its
own control; the largest connected patch where at least two tracks agree.

**Like with like.** "Two of two agree" is a stricter bar than "two of three", so a
two-track null is naturally smaller and would flatter the event. Every null is compared
with the event recomputed on exactly the same tracks, grouped by track set. Both
problems (the 7 day windows and the mixed track counts) were caught while previewing the
windows, before any result was seen.

## Results

### Three tracks (orbits 19, 85, 121)

| Window | After passes | VV largest patch (km2) | VH largest patch (km2) |
|---|---|---:|---:|
| **Event (lag 0)** | 28 Aug to 5 Sep | **0.413** | **0.115** |
| Null lag 1 | 16 to 24 Aug | 0.028 | 0.026 |
| Null lag 2 | 4 to 12 Aug | 0.010 | 0.012 |
| Null lag 3 | 23 to 31 Jul | 0.011 | 0.009 |
| Event over largest null | | 14.9x | 4.5x |
| Empirical p (floor with 3 nulls is 0.25) | | 0.25 | 0.25 |

Track 19 has no clean 12 day history before mid July, so no older three-track windows
exist. The three nulls are in the same late monsoon season as the event, which makes
them the fairest comparison available, and also the fewest.

### Two tracks (orbits 85, 121)

| Window | After passes | VV largest patch (km2) | VH largest patch (km2) |
|---|---|---:|---:|
| **Event (lag 0)** | 28 and 31 Aug | **0.085** | **0.035** |
| Null lag 6 | 22 and 25 Jun | 0.056 | 0.069 |
| Null lag 7 | 10 and 13 Jun | 0.154 | 0.104 |
| Null lag 8 | 29 May and 1 Jun | 0.023 | 0.016 |
| Null lag 9 | 17 and 20 May | 0.088 | 0.093 |
| Empirical p | | 0.60 | 0.80 |

On these two geometries alone the event is ordinary. These nulls fall in May and June,
the snowmelt and monsoon onset season, which the pre-stated caveat expected to be noisier,
so this comparison is harsher than the three-track one. It is still the result: the
two-track signal is not separable from background.

### Where the patches are

| Track set | VV event patch | VH event patch | VV to VH |
|---|---|---|---:|
| 19 + 85 + 121 | 28.3048 N, 85.5030 E | 28.3038 N, 85.5032 E | **0.11 km** |
| 85 + 121 | 28.2862 N, 85.5186 E | 28.2864 N, 85.5188 E | 0.03 km |
| 19 + 121 | 28.2873 N, 85.5276 E | 28.3195 N, 85.4876 E | 5.0 km |
| 19 + 85 | 28.3083 N, 85.4998 E | 28.2875 N, 85.5293 E | 3.5 km |

The three-track patch and the 85 + 121 patch are each found at the same spot by both
polarisations. The 85 + 121 patch is small and not above its nulls, but its position
agreeing to 30 m across polarisations still says that change is on the ground, not noise.

### VV and VH overlap of the full agreement maps

| Windows | Jaccard overlap, VV to VH |
|---|---|
| Event, three tracks | 0.095 |
| Nulls, three tracks (lags 1 to 3) | 0.020, 0.013, 0.015 |
| Event, 85 + 121 | 0.077 |
| Nulls, 85 + 121 (lags 6 to 9) | 0.065, 0.088, 0.036, 0.069 |

## What this changes

* The 2026 three-track result is no longer one comparison against one null. It is first
  among every clean like-for-like null window available, in both polarisations, and the
  two polarisations independently agree on its location to about 100 m.
* It also has an honest ceiling. The evidence rests on three nulls, so "extreme among
  few" is the correct wording, not "significant". And it rests on three viewing
  geometries: two tracks alone do not show it.

## What this does not change

* **n = 1.** No new positive.
* **No lead time.** Nothing here touches the warning path.
* **The location refinement is still untested on the ground** (#28).

## Follow-ups

* More three-track nulls would lift the rank floor below 0.25. The same season in
  earlier years (2025, 2024) on the same tracks is the natural source, and it also
  answers the season-matching question raised in exp012.
* For Thame (#29), use the same windows machinery before drawing any conclusion.
