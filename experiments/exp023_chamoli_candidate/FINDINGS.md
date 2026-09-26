# Experiment 023: is the Chamoli 2021 rock and ice avalanche a second positive? (#6)

**Question.** The positive class is one event. Chamoli, 7 February 2021, is a large and
well recorded rock and ice avalanche with a published seismic origin time. It is about
610 km from NK.KKN and 730 km from IO.EVN, so it can never be a positive for lead time
or fusion. Can the seismic detector see it at all?

**Answer.** No. At 610 km the detector does not trigger, and the second station has no
archive for the date.

| Station | Distance | Result |
|---|---:|---|
| NK.KKN | 610 km | No trigger in the 45 minutes around the origin. Peak STA/LTA 3.98 against a trigger level of 5. |
| IO.EVN | 730 km | No waveform in the archive for February 2021. |

For comparison the same code gives the 2026 event at NK.KKN a peak STA/LTA of 9.5 at
56 km, and at IO.EVN 8.3 at 131 km. On this run's window the IO.EVN 2026 segment came
out a rounding step below its own threshold, as in exp020: a threshold set exactly at
the event's value fails whenever the window is cut differently.

Run 2026-09-26. The Chamoli window on NK.KKN was fetched and is now cached.

## What this says

* **The positive class stays at one.** Chamoli was added to the catalogue as a
  candidate for the seismic classifier only, and it is not visible to the detector at
  this range. The energy of even a very large avalanche falls below the trigger level
  after 600 km through the Himalayan crust on a short period band. Published detections
  of Chamoli used long period, low frequency energy on broadband stations across the
  region, which the 0.5 to 20 Hz analysis band here does not keep.
* **A miss here says nothing about the detector's purpose.** It was built for sources
  inside about 150 km of a station. It does raise a question worth its own experiment:
  whether a lower band would let a station see the *type* of event further away, at the
  cost of more distant earthquakes looking similar.
* **Second positives have to come from inside the station reach,** which means events
  in Nepal or southern Tibet from 2020 on for NK.KKN and from 2014 on for IO.EVN, and
  most of those have already been tried (exp008, exp016, exp020).

## Design

The 45 minute archive window around the published origin on both stations, the
detector, an onset picked against the predicted arrival at the catalogued distance with
a 90 s tolerance, and the decision segment's features and three component descriptors
where a pick exists. The 2026 event was run through the same code in the same run so
the two are on one basis.
