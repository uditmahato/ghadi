# Experiment 021: do the three component features separate the cascade from noise? (#37)

**Question.** Particle motion descriptors were written and tested but never used. Do they
separate the 2026 cascade from the windows the single station spectral test counts as
false alarms?

**Answer.** One of them does, on both stations: the share of energy on the horizontal
channels. The cascade puts about twice as much energy on the horizontals as on the
vertical, and most false alarms do not.

| Descriptor | Station | 2026 value | False alarm median | False alarms at or above 2026 | Windows a rule at the 2026 value would remove |
|---|---|---:|---:|---:|---:|
| Horizontal to vertical, 120 s segment | NK.KKN | 2.32 | 0.99 | 0 of 6 segments | **4 of 4** |
| Horizontal to vertical, 120 s segment | IO.EVN | 1.98 | 1.54 | 7 of 41 | **23 of 29** |
| Horizontal to vertical, 20 s at onset | NK.KKN | 1.81 | 1.08 | 1 of 6 | 3 of 4 |
| Horizontal to vertical, 20 s at onset | IO.EVN | 1.84 | 1.37 | 6 of 41 | 23 of 29 |
| Rectilinearity, 20 s at onset | NK.KKN | 0.86 | 0.74 | 0 of 6 | 4 of 4 |
| Rectilinearity, 20 s at onset | IO.EVN | 0.53 | 0.53 | 21 of 41 | 14 of 29 |
| Incidence angle, 20 s at onset | NK.KKN | 79 deg | 44 deg | 1 of 6 | 3 of 4 |
| Incidence angle, 20 s at onset | IO.EVN | 65 deg | 57 deg | 18 of 41 | 13 of 29 |

* **The horizontal to vertical ratio over the decision segment is the one to use.** At
  NK.KKN the cascade sits above every false alarm segment. At IO.EVN it sits above 34 of
  41. A rule that keeps only segments at or above the cascade's own value would remove
  all 4 NK.KKN false alarm windows and 23 of 29 at IO.EVN.
* **Rectilinearity works at NK.KKN and not at IO.EVN.** At 131 km the arrival is a mix
  of phases and the 20 s onset motion is no more linear than noise. Incidence angle
  behaves the same way. Neither is a general rule.
* **The physics is the expected one.** A shallow surface source seen at tens of
  kilometres arrives mostly as surface waves, which move the ground sideways. Body waves
  from depth, and much local noise, do not.

Run 2026-09-25. The horizontal channels for the 2026 windows and the 33 false alarm
windows were fetched and are now cached.

## What the counts mean, and do not

The thresholds in the last column are the 2026 event's own values, set after looking at
it. They say what a rule at that operating point could remove at best. They say nothing
about how often a real slope failure would fall below it, because there is one real
slope failure to look at. The rule would have to be set with margin below the 2026
value, and every step of margin lets more false alarms through: at IO.EVN, 7 of 41
segments already sit above 1.98, and the median false alarm is 1.54.

The false alarm samples are small: 6 segments in 4 windows at NK.KKN, 41 in 29 at
IO.EVN. These are the windows that already passed the spectral test, so this measures
what the new feature adds on top of it, which is the right question, on a small sample.

## What this means for the product

* **Fetch all three channels in the live loop.** The vertical alone was a choice of
  convenience. The feature that helps needs the horizontals over the decision segment.
* **Add the ratio as a third criterion, with margin, and measure again.** Combined with
  two station agreement (exp019), the surviving false alarms at IO.EVN may reach the
  target. This has not been measured jointly, and the two rules may remove the same
  windows.
* **Do not use rectilinearity or incidence at IO.EVN.** They separate at 56 km and not
  at 131 km, and a rule that depends on distance to an unknown source is not a rule.

## Design

* Three channels for each window, aligned to the shortest, preprocessed as the vertical
  is, with `ghadi.features_3c.polarisation_over_window` over 20 s from the onset and
  `hv_ratio` over the 120 s decision segment.
* The 2026 onset picked as in exp019. False alarm onsets are exp018's passing segments.
* No earthquake corpus in this run. Distant earthquakes are already removed by the
  catalogue check, and the question here was the noise that remains.
