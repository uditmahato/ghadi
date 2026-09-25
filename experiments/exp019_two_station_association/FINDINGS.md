# Experiment 019: does requiring two stations to agree cut the false alarm rate? (#31)

**Question.** The single station spectral test runs at about 14 false alarms per station
month at NK.KKN and 89 at IO.EVN (exp018). If a detection at one station must be matched
by a trigger at the other at a time that fits some source in the region, and then a
source in the 2026 zone, how many false alarms survive, and does the 2026 event itself
survive?

**Answer.** The 2026 event passes every level. The false alarm rate falls by a factor of
4 to 30 depending on how strict the match is, but the second station was missing for a
third of the IO.EVN cases, and the strictest level is tied to one known source area.

| Rule | IO.EVN windows | Per station month | NK.KKN windows | Per station month |
|---|---:|---:|---:|---:|
| Single station (exp018) | 29 | 88.7 | 4 | 13.7 |
| Other station triggers at a time fitting any source in the region | 7 | 21.4 | 3 | 10.3 |
| Same, and the matched segment passes the other station's spectral test | 3 | 9.2 | 2 | 6.9 |
| Other station's trigger time fits a source in the 2026 zone | 3 | 9.2 | 0 | 0.0 |
| Same, and the matched segment passes the spectral test | **1** | **3.1** (0.1 to 17.0) | **0** | **0.0** (0 to 12.6) |

Windows where the other station had no waveform are not in the counts: 11 of 29 for
IO.EVN and 1 of 4 for NK.KKN. Station months are the full exp018 values.

* **The 2026 event is consistent across the two stations.** NK.KKN picks the onset at
  02:52:30.3 UTC and IO.EVN at 02:52:43.1, a difference of 12.8 s. Every grid point in
  the catalogued 8 km zone can explain that difference at some speed between 2.5 and
  6.5 km/s.
* **The association test on its own is weak.** The 2026 pair would have accepted 40% of
  the search region, about 14,000 km2, because the allowed speed range is wide and the
  stations are far apart. Requiring the other station to see it at all is what removes
  most false alarms, not the geometry.
* **NK.KKN false alarms never fit the 2026 zone.** All three that had IO.EVN data were
  matched by some IO.EVN trigger, but never at a time that put the source in the zone.
  This is the first rule under which NK.KKN reaches the target of 1 per station month,
  though 0 in 0.29 station months only bounds the rate below 12.6.
* **IO.EVN drops from 89 to about 3 per station month at the strictest level.** One
  window survives, 25 May 2024, in which both stations trigger, the times fit the zone,
  and both segments look like a mass movement. That may be a real event that never
  reached a river. It was not checked further here.

Run 2026-09-25. The 2026 picks came from the cached windows; the other station's
waveforms for the 33 false alarm windows were fetched and are now cached.

## What the missing station changes

The second station is a dependency, and it was absent 38% of the time for IO.EVN's
false alarms (11 of 29 windows, all between November 2024 and January 2026, when the
NK.KKN archive has gaps). In operation a missing partner means the rule cannot be
applied, and the system has to say which it does: fall back to the single station rate,
or refuse to raise the seismic channel above quiet. If those 11 windows are counted as
surviving, the strictest IO.EVN rate is 12 windows, 36.7 per station month. The true
operational number lies between 3.1 and 36.7, and depends on NK.KKN's uptime.

## What the zone test is, and is not

The zone here is the 2026 source circle: 8 km around 28.255 N, 85.520 E. Asking whether
a pair of picks fits that circle asks whether the same place failed again. That is a
fair question for the Lhende Khola, and it is not the product's question, which is
whether anything failed upstream of a settlement. The right test uses a basin outline,
which is larger than one circle and smaller than the whole region, so its false alarm
rate sits between the second and fourth rows of the table. Building that outline needs
river geometry the repository does not yet hold.

## Design

* Onsets on both stations for 2026 from the cached windows, with the picker of exp005
  and exp010 (closest trigger to the predicted P arrival, no pre origin triggers).
* Search region 27.4 to 29.0 N, 84.6 to 86.6 E on a 4 km grid, 2,205 points. Speed
  range 2.5 to 6.5 km/s, tolerance 5 s each side.
* For each exp018 false alarm window, the other station's 35 minute window, the same
  detector, and ``ghadi.associate.arrival_bracket`` for each passing segment's onset.
  Zone consistency uses ``ghadi.associate.associate`` on the matched pair.
* Rates on exp018's station months, exact Poisson 95% intervals.

exp008 did a version of this by hand for the older catalogue events. This puts it in the
library and prices it on noise.

## What this means for the product

* **Two stations agreeing is the strongest lever found so far,** and NK.KKN's false
  alarms all fail the zone test. This is the rule the live loop should apply to the
  seismic channel: agreement raises it, disagreement or an absent partner keeps it
  where a single station leaves it.
* **It buys nothing for fusion's second group.** Two seismometers share a failure
  mode. The gauge (#27) is still the only independent source.
* **The next step is the basin outline,** not a tighter speed range. A tighter range
  needs phase identification the picker cannot do.
