# Experiment 030: are there uncatalogued slope failures in the 2015 to 2016 network data?

**Question.** The positive class is one event. From June 2015 to May 2016 a temporary
network had twelve stations with long period channels within about 100 km of the 2026
source, in the year after the Gorkha earthquake. A large mass movement carries strong
energy below 0.1 Hz (exp029). Does a scan of that band across the network turn up
events that no earthquake catalogue explains and that look like slope failures?

**Answer.** No. The scan works, and it finds 263 long period events the catalogue does
not explain, but on a closer look none of them is a slope failure. The positive class
stays at one.

| Step | Count |
|---|---:|
| Station days scanned | 2,844 |
| Long period events seen by at least four stations | 1,195 |
| Explained by a catalogued earthquake | 932 |
| Unexplained | 263 |
| Unexplained and much stronger at one station than the rest ("local") | 46 |

The 46 local ones and the 30 strongest of the others, looked at in the short period
record at their two strongest stations:

| What the short period record shows | Local (46) | Others (30) |
|---|---:|---:|
| An arrival that fails the mass movement rule (earthquake like) | 34 | 16 |
| No short period arrival at all | 11 | 13 |
| Mass movement like at one station | 1 | 1 |
| Mass movement like at both stations | **0** | **0** |

Run 2026-10-03. The long period data, the catalogue, and the short period windows are
cached.

* **The scan is sensitive.** Of 125 catalogued earthquakes of M6 and above in the
  period, 107 appear as candidates, 86 percent. The rest fell in gaps: the nearest
  station has data for only 53 percent of the period.
* **Most of what the catalogue leaves is still earthquakes.** 50 of the 76 inspected
  have a short period arrival that the project's rule calls earthquake like. This was
  the year after an M7.8, and the global catalogue does not hold the thousands of small
  aftershocks under the network.
* **A quarter are not ground motion at all.** 24 have a long period transient and
  nothing in the short period band. That is what a sensor settling, a temperature
  step, or a visit to the station looks like.
* **The one local candidate does not survive its neighbours.** On 30 March 2016 at
  10:56 UTC station NA090 recorded a strongly low frequency arrival that passes the
  rule, with a horizontal to vertical ratio of 34. A station 13 km away saw 2 times its
  ordinary level while one 76 km away saw 62. A real source near NA090 would fade with
  distance; this does not. The extreme horizontal ratio points to the sensor tilting.
  The other "like" case is a single station with nothing at the network's strongest
  one.

## How small an event this could have found

A candidate needs four stations at 4 times their ordinary long period level. The 2026
event gave ratios of several hundred to two thousand at 56 and 131 km (exp029). So an
event with one or two percent of the 2026 long period amplitude, anywhere inside the
network, would have been listed. That is a rough figure: it compares two slightly
different ratios and assumes a source of the same kind. What it rules out is a second
event of anything like the 2026 size in central Nepal between June 2015 and May 2016.
It does not rule out the many small rain triggered slides of the 2015 monsoon, which
move far less mass and may reach only one or two stations.

## What this means

* **Open seismic archives do not hold a second event of this kind for this region.**
  exp008 searched the catalogued events, exp016 the radar record, exp023 an event in a
  neighbouring range, and this the densest year of data that exists. Each came back
  without one. A second positive will come from the future, from the shadow service
  running, or from data the project does not yet have access to.
* **The claims have to stay shaped for n = 1.** The injection curve (exp026) is the
  miss side estimate the project can make, and it is an estimate for one event shape.
* **The scan itself is reusable.** A long period network scan with a catalogue check
  and a short period look is a working method for any network and period. It is the
  natural tool if the national network's data becomes available.

## Limits

* The short period rule's thresholds are NK.KKN's at the default margin and were never
  set for these stations. "Earthquake like" means only that the rule did not pass.
* Requiring four stations hides anything small. That is by design, and it is why this
  is a search for events like 2026 and not for landslides in general.
* The catalogue rule (M5.0 anywhere, M4.5 within 45 degrees, M4.0 within 20 degrees)
  was widened once, after the first run left M4.5 to M5 earthquakes at 20 to 45 degrees
  unexplained. That took the unexplained count from 362 to 263.

## Design

`run.py`: the 1 sample per second vertical channel of twelve stations, band passed 0.02
to 0.08 Hz, envelope over the day's median, at least four stations and half of those
reporting at 4 times their level within a minute, merged into events, and each event's
peak tested against catalogued phase windows. `inspect_candidates.py`: twenty minutes
of the 100 or 200 sample per second record around each candidate at its two strongest
stations, through the project's detector, decision segment, and classifier.
