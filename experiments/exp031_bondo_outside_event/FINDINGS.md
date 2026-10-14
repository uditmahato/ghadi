# Experiment 031: does the detector see a mass movement outside Nepal?

**Question.** The Nepal positive class is one event, and the thresholds were set on it.
Is the low frequency signature a property of this kind of source, or of one event seen
by two stations? On 23 August 2017 about three million cubic metres of rock fell from
Piz Cengalo, Switzerland, at about 07:30 UTC, and turned into debris flows that reached
Bondo. The Swiss network recorded it on many stations, two of them at almost the same
distances as the Nepal pair. What does the project's method make of it?

**Answer.** The low frequency tendency travels. The thresholds and the H/V rule do not.
At every one of five stations the rock avalanche is lower in frequency than the typical
local earthquake, and at four of them no more than about 15 percent of earthquakes reach it, the same kind
of overlap Nepal shows. But the Nepal rule, used unchanged, passes it at only one
station of five, so the system as configured for Nepal would not have flagged Bondo.
The ratio of horizontal to vertical energy, which separated the 2026 event in Nepal,
does not separate this one at all.

Run 2026-10-14. Swiss catalogue and waveforms from the ETH service, cached.

## Results

The 120 s decision segment from the picked onset, as in exp005 and exp010. The
comparison population is the 50 largest catalogued earthquakes (M2.8 to M4.6) within
1.4 degrees of the source, 2014 to 2021, each measured the same way on the same station.

| Station | Distance | Onset (UTC) | LF/HF | Centroid | H/V | Nepal rule | Earthquakes meeting both spectral values |
|---|---:|---|---:|---:|---:|---|---:|
| CH.VDL | 23 km | 07:30:19.4 | 3.87 | 2.23 Hz | 1.42 | fail | **0 of 49** (0%) |
| CH.DAVOX | 58 km | 07:30:25.2 | 1.10 | 2.93 Hz | 1.84 | fail | 11 of 50 (22%) |
| CH.MUGIO | 59 km | 07:30:33.2 | 3.02 | 2.53 Hz | 1.65 | fail | 4 of 49 (8%) |
| CH.MMK | 128 km | 07:30:49.7 | 2.50 | 2.70 Hz | 1.62 | fail | 7 of 49 (14%) |
| CH.SGT05 | 128 km | 07:30:52.1 | 6.77 | 1.99 Hz | 1.93 | **pass** | 7 of 46 (15%) |

For comparison, the 2026 event: 17.2 percent overlap on NK.KKN at 56 km (exp005) and
4.5 percent on IO.EVN at 131 km (exp010).

| Station | Earthquake median LF/HF | Earthquake median centroid | Earthquakes with H/V at or above the avalanche's | Earthquakes passing the Nepal rule |
|---|---:|---:|---:|---:|
| CH.VDL | 0.39 | 4.92 Hz | 30 of 49 | 0 |
| CH.DAVOX | 0.71 | 3.99 Hz | 25 of 50 | 0 |
| CH.MUGIO | 0.45 | 4.72 Hz | 26 of 49 | 0 |
| CH.MMK | 0.75 | 3.97 Hz | 32 of 49 | 0 |
| CH.SGT05 | 1.71 | 3.32 Hz | 11 of 46 | 4 |

Earthquakes at half to one and a half times the avalanche's distance from each station,
the fairer comparison because the features change with distance: DAVOX 5 of 25, MUGIO
0 of 6, MMK 3 of 24, SGT05 3 of 30. No earthquake falls in that band for VDL.

## What it shows

* **The tendency is a property of the source.** A rock avalanche in the Alps, recorded
  by a different network on different ground, sits in the low frequency tail of its own
  region's earthquakes, as the 2026 event does in Nepal. Its LF/HF is 1.5 to 10 times the
  local earthquake median at every station. This is the strongest outside support the
  project's premise has had, and it does not depend on the Nepal thresholds.
* **It is a tendency, not a boundary, here too.** Up to 22 percent of earthquakes reach
  the avalanche's values at one station. That matches NK.KKN's 17 percent, so the paper
  can say the overlap is typical rather than a Nepal problem.
* **The thresholds do not travel.** They are absolute values from one event on two
  stations. Four of the five Swiss stations fall short of them, while their own earthquake
  populations sit lower too. A deployment on another network needs thresholds set on
  that network's earthquakes. Set relative to each station's own earthquake population,
  the avalanche would stand out at most stations; set at the Nepal values, it does not.
* **The H/V rule does not travel.** The avalanche's H/V is near the median of the local
  earthquakes at every station, and above it at none by much. In Nepal the 2026 event put
  about twice as much energy on the horizontals (exp021). Either that was a property of
  the Nepal sites and paths, or of the 2026 source, an ice and rock avalanche that became
  a flood down a long valley. One Alpine event cannot tell which, but the rule must not be described
  as a general mark of mass movements.
* **Which arrival triggers changes the spectrum.** DAVOX and MUGIO are the same distance
  from the source, yet DAVOX triggered 8 s earlier, on what is most likely the first
  arrival, and measured an LF/HF of 1.10 against MUGIO's 3.02. The two far stations
  triggered later, on the stronger waves, and both show the low frequency signature. For
  an emergent source the 120 s segment's content depends on where the trigger fires.

## What it does not show

* **It is not a second Nepal positive.** The Nepal count stays at one. Bondo is a test of
  the method on another event, not a new label for the Nepal detector.
* **It is one Alpine event.** The comparison is between one avalanche and one region's
  earthquakes. It shows the tendency can appear elsewhere, not how often.
* **Sizes differ.** Bondo was about three million cubic metres. The comparison does not
  rest on the two events being alike in size, only on each being compared with its own
  region's earthquakes.
* **The catalogue's earthquakes are mostly small and local**, M2.8 to M4.6 within about
  200 km, while the Nepal corpora reach further and larger. Each comparison is within one
  station, so this does not mix the two, but the two overlap figures are not on exactly
  the same basis.

## What this means for the project

* The paper can claim that the low frequency signature appeared on a second mass
  movement in a different mountain range and network, with an overlap like Nepal's.
* It must also say that the operating thresholds and the H/V rule are local, and that
  the Nepal system as configured would have missed Bondo.
* A rule stated relative to each station's own earthquake population, for example a
  percentile, would carry between networks better than absolute values. That is a
  follow up to test, not a change to make on this evidence.

## Design

`run.py`: the five stations' `HH?` channels from the ETH service, 300 s before to 480 s
after the reported time for the avalanche and the catalogued origin for each earthquake.
The avalanche's onset is the strongest trigger between 120 s before and 240 s after the
reported time; an earthquake's is picked against its origin and distance
(`ghadi.detect.pick_onset`). Features over the 120 s segment from the onset
(`ghadi.features.extract`), H/V over the same segment (`ghadi.features_3c.hv_ratio`),
and the Nepal rule from `ghadi.classify.classify_segment` with the default
configuration. The first run rejected windows whose data began a little before the
requested time; they are now cut to the request first, and the table above is from the
corrected run.
