# Experiment 018: what false alarm rate does the detector run at on IO.EVN? (issue #3)

**Question.** The only measured false alarm rate was NK.KKN's, 6.8 per station month
(exp009), computed from whole window features. IO.EVN, the Everest station 131 km from
the 2026 source, has its own site, noise, and thresholds. What rate does it run at, and
what is NK.KKN's rate on the same decision time basis?

**Answer.** Both stations are far above the target of 1 per station month, and IO.EVN is
much worse.

| Station | Hours of noise | Windows with a trigger | False alarm windows | Per station month | 95% interval |
|---|---:|---:|---:|---:|---:|
| IO.EVN | 238.6 | 372 of 409 | 29 | **88.8** | 59.5 to 127.5 |
| NK.KKN | 213.5 | 108 of 366 | 4 | **13.7** | 3.7 to 35.0 |

* **IO.EVN runs at about 89 false alarms per station month.** That is roughly one every
  eight hours. Nearly every window (372 of 409) has at least one STA/LTA trigger, so the
  spectral test does almost all of the work, and it passes 29 windows even at IO.EVN's
  strict looking LF/HF threshold of 15.
* **NK.KKN is about twice as bad as exp009 said, once measured the same way.** On the
  decision time basis (the 120 s after each trigger) NK.KKN gives 13.7 per station
  month. The whole window basis, recomputed from the same cache, still gives 6.8 and
  matches exp009 exactly. The difference is the basis, not the data: a short segment
  after a trigger is more often dominated by low frequency energy than a 35 minute
  window. The decision time basis is what the detector actually sees, so 13.7 is the
  more honest number.
* **These are lower bounds.** Each station's thresholds are the 2026 cascade's own values
  at that station, fitted to the one positive event. That is the most permissive
  operating point that still catches it.

Run 2026-09-17. Probability of detection is still not estimable (n = 1), so these rates
are half of a trade off curve and must not be quoted as detector performance.

## Design

* **Corpus.** `scripts/harvest_noise.py --station IO.EVN`, the same design as NK.KKN's
  committed corpus: 2024-01 to 2026-07, months the coverage probe found present, 6 hour
  cells, 3 windows per cell, seed 0, 35 minute windows. Regional earthquakes and global
  teleseisms are excluded by the shared phase window rule. Of 486 candidates, 409 were
  usable, 39 had no waveform, 28 overlapped a teleseism, and 10 overlapped a regional
  event. Saved as `data/corpus/noise_IO_EVN.json`.
* **Basis.** For every trigger, the spectral features of the 120 s segment after its
  onset (up to 20 triggers per window). A window counts as a false alarm if any segment
  shows a signal and meets the station's thresholds.
* **Thresholds.** NK.KKN LF/HF at least 4.92 and centroid at most 1.89 Hz (exp005).
  IO.EVN LF/HF at least 15.07 and centroid at most 1.53 Hz (exp010).
* **NK.KKN like with like.** Its committed windows were reprocessed from the local
  waveform cache with per trigger segments. The committed corpus file was not changed.
  Every recomputed whole window feature matched the committed value.
* **Uncertainty.** Exact Poisson 95% interval on each count.

The harvest script now takes `--station`, and its default windows per cell was
corrected from 4 to 3 so that it reproduces the committed NK.KKN corpus exactly (all 435
candidate windows).

## What the IO.EVN false alarms look like

* **No season and no time of day.** The 29 windows fall in 11 of 12 calendar months and
  in all six 6 hour cells, with a mild excess in the cell starting 04 UTC (8 of 29). This
  does not look like a single daily source such as afternoon melt or valley wind.
* **Strongly low frequency.** Passing segments have LF/HF from 15 to 463 and centroids
  from 0.75 to 1.49 Hz. Across all 1027 signal present segments the median LF/HF is 1.9
  and the 99th percentile is 71, so the cascade's value of 15 at IO.EVN sits well inside
  the noise tail: 44 segments reach it.
* **Likely causes, not tested here.** Everest is a high alpine site surrounded by
  glaciers, icefalls, and steep rock walls. Ice and rock falls, serac collapse, and
  glacier quakes are all low frequency mass movement sources in their own right. Some
  of these "false alarms" may be real mass movements that simply did not become floods.
  That makes them wrong alarms for a flood warning, but it also means a spectral shape
  test alone cannot tell them apart.

## What this means

* **A single station spectral test is not a usable warning channel at IO.EVN.** At 89
  per station month the seismic channel on its own would train people to ignore it. It
  can only contribute as corroboration, which is how fusion already uses it: one
  seismic channel is held below WARNING, and exp017's strict rule would also stop a
  quiet channel from counting as support.
* **The exp009 headline for NK.KKN should be read as 13.7, not 6.8.** The 6.8 figure is
  not wrong, but it is on a basis the live detector does not use.
* **The next lever is not a threshold.** Raising IO.EVN's LF/HF bar would soon exclude
  the 2026 cascade itself. What is missing is information that separates a flood source
  from other low frequency sources: duration, amplitude against distance, a second
  station agreeing on location, or the downstream gauge.

## Limits

* 0.33 and 0.29 station months are short. The intervals are wide and the IO.EVN lower
  bound (59.5) is the safest number to quote.
* Windows are sampled, not continuous, so clustered noise days could push the real rate
  either way.
* The teleseism and regional exclusions remove some of the most energetic windows, as
  they would be removed in operation.
