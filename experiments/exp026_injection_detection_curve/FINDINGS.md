# Experiment 026: how small an event would the system still catch?

**Question.** Every number so far is on the false alarm side. With one real event the
miss side cannot be counted. It can be estimated by scaling the 2026 waveform down,
adding it to real noise from the same station, and asking the live decision function
whether it still says "mass movement like".

**Answer.** An event shaped like 2026 is caught half the time at about 2.5 percent of
its amplitude and nine times in ten at about 10 percent. Without the 20 percent margin
on the thresholds the same system catches almost nothing, at any size.

| Size, share of 2026 | Trigger found | Detected, 20% margin | Detected, no margin | Detected and corroborated by IO.EVN |
|---:|---:|---:|---:|---:|
| nothing injected | 0% | 0% | 0% | 0% |
| 2% | 32% | 32% | 0% | 30% |
| 3% | 71% | 70% | 0% | 66% |
| 5% | 84% | 84% | 0% | 82% |
| 8% | 89% | 89% | 8% | 88% |
| 12% | 89% | 89% | 21% | 88% |
| 20% | 93% | 93% | 33% | 92% |
| 30% | 97% | 97% | 23% | 97% |
| 50% | 99% | 98% | 8% | 98% |
| 100% | 100% | 98% | 2% | 98% |

120 noise windows from the NK.KKN corpus, each with every size injected. Run 2026-10-01.
The horizontals and the IO.EVN vertical for those windows were fetched and are now
cached.

* **The trigger is the limit, not the classifier.** At every size the share detected
  is within a point of the share that triggered. Once the detector fires on the
  arrival, the spectral and H/V rules pass it. Sensitivity is set by the STA/LTA
  threshold and the noise, and the rules after it cost nothing on this event shape.
* **The floor is about one fortieth of the 2026 amplitude.** Half of the windows catch
  a 2.5 percent copy. The remaining misses at larger sizes, about 1 in 10 between 8 and
  12 percent, are windows where the noise already holds the long average up.
* **The margin is not optional.** With thresholds at the event's own values the full
  size event is caught in 2 percent of windows, and the best case is 33 percent. Real
  noise moves the features by more than zero, and zero is the margin those thresholds
  had. exp020 saw this once by accident; this shows it is the rule.
* **The partner station costs almost nothing on the miss side.** IO.EVN triggers at a
  fitting time in every window with an injection, because the 2026 signal was much
  stronger there relative to its noise. Detection with corroboration is within a few
  points of detection without. With nothing injected it still "corroborates" 19
  percent of the time, which is IO.EVN's own trigger rate inside the bracket: the
  partner rule's power comes from the primary detection, not from the partner alone.
* **No false detection in the control.** With nothing injected, none of the 120
  windows produced a detection at the injection slot.

## What the sizes mean

Amplitude at a station falls with distance and rises with the size of the failure. A
copy at 10 percent of the 2026 amplitude is, very roughly, the same event three times
further away under geometric spreading alone, or a much smaller event at the same
distance. Neither conversion is measured here, and real attenuation removes high
frequencies as well as amplitude, which changes the shape. So the table is a statement
about amplitude at NK.KKN, and the conversion to source size or distance is future
work.

## What this does not show

* **Other shapes.** A scaled copy of one event is one shape at ten sizes. A slower,
  shorter, or more distant failure has a different spectrum and this says nothing
  about it. A lake outburst (exp016, exp020) is exactly such a case.
* **The whole chain.** Detection here stops at the seismic decision. The catalogue
  check would set aside the 7 percent of the time a distant earthquake is passing
  (exp024), and the gauge is not modelled.
* **A first attempt was wrong, and is recorded.** With the template starting 20 s
  before the onset, the full size event was "caught" only 34 percent of the time. The
  template's own background noise, added to a quieter window, tripped the detector 15 s
  early and outside the tolerance. The template now starts 3 s before the onset.

## Design

`ghadi.live.observation_from_window`, the function the shadow service calls, on the
240 s window holding the injected onset at 90 s, with the horizontals. Detected means
a trigger within 15 s of the injected onset whose segment classifies as mass movement
like. The IO.EVN copy is injected 12.8 s later, as observed in 2026 (exp019), at the
same factor.
