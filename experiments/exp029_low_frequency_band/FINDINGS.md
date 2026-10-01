# Experiment 029: can a lower frequency band see this kind of event from further away?

**Question.** The detector works in 0.5 to 20 Hz and did not see the Chamoli 2021 rock
and ice avalanche at 610 km (exp023). Is Chamoli visible at NK.KKN in a lower band, is
the 2026 event visible there too, and how often does ordinary noise look the same?

**Answer.** Chamoli shows faintly between 0.05 and 0.5 Hz, where 2 of 150 noise windows
do as well, and not at all in the working band. The 2026 event is enormous in every
band, and at the further station it is strongest in the lowest ones.

Signal to noise in the surface wave window. In brackets: the 95th percentile of 150
noise windows at the same station and geometry, and the empirical rank.

| Band | Chamoli 2021 at NK.KKN, 610 km | 2026 at NK.KKN, 56 km | 2026 at IO.EVN, 131 km |
|---|---:|---:|---:|
| 0.5 to 20 Hz (working band) | 3.4 (3.7, p 0.07) | 371 (2.8, p 0.007) | 304 (7.3, p 0.007) |
| 0.1 to 0.5 Hz | **2.7** (1.9, p 0.013) | 210 (1.9, p 0.007) | 196 (2.2, p 0.013) |
| 0.05 to 0.1 Hz | **5.1** (3.1, p 0.013) | 475 (2.8, p 0.007) | 1325 (2.6, p 0.007) |
| 0.02 to 0.05 Hz | 0.9 (2.9, p 0.87) | 84 (2.3, p 0.007) | 2130 (3.6, p 0.007) |

Run 2026-10-01, offline from the cache. With 150 noise windows the lowest possible
rank is 0.007.

* **Chamoli is above the noise in two low bands and not in the working band.** In 0.05
  to 0.1 Hz its ratio is 5.1 against a 95th percentile of 3.1, with one noise window
  higher. In 0.1 to 0.5 Hz it is 2.7 against 1.9. The two bands are neighbours on one
  record, so this is one weak observation, not two. It is consistent with the published
  long period detections of that event and does not confirm it independently.
* **The 2026 event carries strong long period energy.** At IO.EVN its ratio rises from
  304 in the working band to over 2,000 below 0.05 Hz. A large mass moving down a slope
  pushes on the ground for tens of seconds, and that push is long period. It is the
  expected signature and it is very clear.
* **A low band reaches further.** Short period energy from Chamoli is gone by 610 km.
  Its long period energy is not. A detector with a second, lower band could see events
  of this kind several times further away than the current one.
* **It would also see every distant earthquake.** The noise maxima in the low bands at
  IO.EVN reach 59 and 880, from earthquakes below the corpus's M5.5 exclusion. A low
  band channel is only usable behind the catalogue check, and exp024's lower threshold
  becomes more important, not less.

## What this does not show

* **A detector.** This is a ratio at a known origin time and distance. Finding an
  event without knowing when or where is a different problem, and in this band it is
  the problem of telling a landslide from an earthquake by the shape of a long period
  pulse, which this project has not attempted.
* **A second positive.** Chamoli's rank of 0.013 on one station is suggestive. It is
  not enough to add to the positive class.

## What it suggests

A second, long period channel (0.02 to 0.1 Hz) computed on the same stations, used as
corroboration for the short period detector at first: a real slope failure of size
should show in both, and most local short period noise shows only in one. That is a
new experiment with its own false alarm measurement.

## Design

Zero phase band pass, envelope smoothed over two periods of the band's lowest
frequency, peak in the window where a wave travelling 2.5 to 4.5 km/s arrives (plus
120 s), over the median envelope of the nine minutes before the origin. The same
statistic at the same window geometry on 150 noise windows from the same station.
