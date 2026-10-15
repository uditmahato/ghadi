# Detecting river blocking mass movements with open seismic stations: the 26 August 2026 Bhote Koshi flood surge

*What a single event can and cannot tell us about flood warning*

First full draft, 14 October 2026. Every number is from an experiment in this
repository, named in brackets so it can be checked and rerun. Placeholders for results
still to come are marked **TO COME**. The reference list is [REFERENCES.md](REFERENCES.md).

---

## Abstract

On 26 August 2026 an ice and rock avalanche in the Lhende Khola blocked and then
released the Bhote Koshi, and the surge that followed down the Trishuli left more than a
thousand people dead. Four of five downstream river gauges were destroyed before their
thresholds triggered. We ask whether open seismic stations could have given warning
instead. The mass movement was recorded by the one open broadband station in Nepal,
56 km away, and by a station in the Everest region 131 km away. Over the first 120 s
after its onset, its signal is richer in low frequencies than that of most regional
earthquakes on both stations, but the separation is a tendency, not a boundary: with
the safety margin the detector uses, 14 of 64 earthquakes pass the spectral rule. A
detector built on spectral shape, the ratio of horizontal to vertical energy, the
screening of distant earthquakes against a live catalogue, and agreement between the
two stations inside the catchment decides about 2.6 minutes after onset. That leaves
roughly 35 minutes of warning at Bidur and 8 at Syabrubesi, while Timure, 4 minutes
downstream, cannot be warned by any detector. Counting the times the second station is
missing, the system raises about 3 false alarms per station month at the Nepal station
and 15 at the Everest one. Injected copies of the 2026 signal are caught half the time
at 2.5 percent of its amplitude. The 2017 Piz Cengalo rock avalanche in Switzerland
shows the same low frequency tendency against its own region's earthquakes on five
stations, but the Nepal thresholds pass it at only one, so the operating rule is local
while the signature is not. The 2015 Taan Fiord landslide in Alaska, twenty times larger,
stands beyond every local earthquake on four stations. A search of catalogued events, satellite radar, a
neighbouring range, and a year of dense network data from 2015 to 2016 found no second
event of this kind in the region, so every estimate rests on one positive case. We
release the code, the data and a shadow service that runs the detector live without
sending alerts, and argue that the method is ready to be tested on national network
data, not to be relied on by itself.

---

## 1. Introduction

Floods that start as mass movements are among the deadliest hazards in the Himalaya. A
slope or glacier fails, the debris blocks a river or becomes a flow, and a surge travels
down valleys where people live close to the water. The 2021 Chamoli disaster began with
about 27 million cubic metres of rock and ice falling from Ronti Peak and left over 200
dead or missing (Shugar and others, 2021). The 2021 Melamchi flood cut up to about 100 m
into high valley fills, set off new landslides and buried the lower valley in sediment
(Chen and others, 2025). The 2023 South Lhonak outburst in Sikkim released about 50 million
cubic metres of water after a moraine collapsed into the lake (Sattar and others, 2025).
On 26 August 2026 an ice and rock avalanche in the Lhende Khola sent a surge down the
Bhote Koshi and the Trishuli.

Such floods are hard to warn for. Many start on a dry day with no weather to watch. River
gauges see the water only when it arrives, and the first gauges are often destroyed: in
2026 four of five were lost before their thresholds triggered. What does reach the
valley before the water is the ground motion. A large mass movement shakes the ground
the moment it starts, and seismometers tens of kilometres away record it within
seconds.

That this signal can be seen is not new. Large landslides are recorded at great
distances (Ekström and Stark, 2013), and the seismic record has been used to
reconstruct landslide dynamics (Hibert and others, 2014), outburst floods in this same
valley (Cook and others, 2018), and the Chamoli cascade on a regional network in India
(Cook and others, 2021). That last study concluded that regional networks could detect
such events from up to 100 km away and give warnings within minutes, and that doing so
in real time needs automated detection that does not yet exist. Dense local networks
already warn of debris flows in instrumented catchments such as the Illgraben
(Chmiel and others, 2021).

What has been missing is the operational test: an automated detector, run on the open
stations that actually exist in Nepal, with its decision time, its false alarm rate,
and its misses measured rather than assumed. This paper reports that test on the 2026
event. It also faces the problem that limits every such study: the positive class here
has one member. We say what one event can support, search for a second, test the method
on two well recorded events elsewhere, and state which claims stand and which do not.

## 2. The event and the data

**The 2026 cascade.** The origin is placed at 02:52:10 UTC on 26 August 2026 (08:37 Nepal
time), refined from the Kakani trigger onset minus about 15 s of travel over 55.9 km
[exp001]. Published accounts give only a time between 08:37 and 08:40. The USGS first
catalogued the signal as an M4.4 earthquake before identifying it as landslide
generated. As of 2 September, 1,058 people had been recovered dead and 4,606 were still
missing; these figures were provisional. There was no rain on the day.

**Where it started.** The catalogued point, 28.255 N 85.520 E, carries an 8 km
uncertainty. Sentinel-1 radar puts the change in one place: a connected patch of
0.41 km² where at least two of three satellite tracks see change in the event window
and not in their own earlier passes, against 0.075 km² for the same test on the weeks
before the event, 5.5 times larger [exp013]. The patch is centred at 28.305 N 85.503 E,
5.8 km from the catalogued point and inside its uncertainty. Against the same late August
weeks of 2022 to 2025, the three track patch is ten times the largest of 13 like for like
windows, though a comparison on two tracks alone does not stand out (Figure 6) [exp015].

**Stations.** Two open broadband stations recorded the event (Figure 1). NK.KKN at
Kakani (27.800 N 85.279 E, 2,042 m, 50 samples per second) is 56 km from the source.
IO.EVN in the Everest region is 131 km away. Of 33 broadband stations in the open
catalogue within 300 km, 31 belonged to a temporary network that closed in 2016; the
two in use are the only two that remain [exp028].

**Earthquake and noise corpora.** For each station, regional earthquakes from the USGS
catalogue were fetched and their onsets picked against the catalogued origin and
distance, rejecting triggers that precede the origin [exp003, exp007]. This gives 64
usable earthquakes on NK.KKN and 132 on IO.EVN. Noise corpora of 35 minute windows
drawn from January 2024 to July 2026, three per month at each of six hours of the day,
give 0.29 station months at
NK.KKN and 0.33 at IO.EVN after windows containing catalogued earthquakes are removed
[exp009, exp018].

**The catchment.** The catchment draining to Bidur, 4,763 km², was derived from the
Copernicus GLO-90 elevation model by priority flood routing and is committed with the
code. It is used to ask whether a pair of station arrivals fits a source upstream of
the settlements [exp022, exp027].

## 3. Method

The detector runs on the stream as it arrives. Its design follows from what each
experiment showed, and every choice is traceable to one.

**Windows and trigger.** Samples are cut into 240 s windows starting every 60 s and band
passed from 0.5 to 20 Hz. An STA/LTA trigger (Allen, 1978) with a 5 s short window and a
60 s long window opens at a ratio of 5 and closes at 2. The first long window of every
analysis window is discarded while the average settles, and the taper is a fixed 5 s
rather than a share of the window, because a fractional taper manufactured triggers
[exp001].

**Decision segment.** Features are measured over the 120 s after the trigger onset, and
a decision is made only on a window that holds the whole segment. Features over a longer
window flatter the separation and are not available when the alert must be made
[exp005]. This sets the decision time: the segment, plus the feed delay, plus up to a
minute until the window that holds it closes. Its floor is about 126 s and its median
in replay about 156 s [exp020]. The segment starts at the first trigger. Four other start
rules, among them the strongest trigger, a later start and a 180 s segment, were tested
on the three events and on 649 earthquakes measured the same way; none passed the events
at more stations, and every later start let more earthquakes through [exp034].

**Spectral rule.** Two features: the ratio of energy below and above 3 Hz (LF/HF), and
the spectral centroid. The split frequency changes the ratio by about three times and
is published with every value [exp001]. A segment passes when its LF/HF is at least,
and its centroid at most, the 2026 event's own values on that station, loosened by 20
percent: on NK.KKN LF/HF of at least 3.94 and a centroid of at most 2.26 Hz. The rule is
a conjunction of thresholds, never a weighted score [exp001]. Without the margin the
live path missed the 2026 event at IO.EVN by a rounding step [exp020], and the injected
event was caught almost never [exp026].

**Horizontal to vertical ratio.** Over the same segment, the square root of the ratio
of horizontal to vertical energy (after Nakamura, 1989). The 2026 event put about twice
as much energy on the horizontals as most false alarms did, on both stations [exp021].
The rule requires at least 80 percent of the event's value.

**Distant earthquakes.** A distant earthquake can look like a slow local source in this
band [exp004]. Each decision is checked against a rolling global catalogue fetched every
two minutes: a trigger inside the window from the P arrival to the end of the surface
waves of an M5.5 anywhere, or an M5.0 within 80 degrees, is set aside [exp006]. The
second tier matters: earthquakes between M5.0 and M5.5 are a third to a half of the
false alarms that survive at IO.EVN, and admitting them within 80 degrees explains 10 of
29, at the cost of setting aside 7.2 percent of the time [exp024]. Because catalogues publish minutes after the waves
arrive, the service also looks again at decisions it has already made and marks any
that a later origin explains [exp025].

**Partner station.** A detection at one station is corroborated when the other station
triggers at a time that fits a source inside the catchment for some speed between 2.5
and 6.5 km/s [exp019, exp022]. Agreement raises the seismic channel's weight; it never
counts as an independent second source, because both stations see the same ground
[exp019].

**Fusion and the human gate.** A seismic detection alone is an Advisory. A Warning needs
a second independent group, in practice a river gauge. A channel that reports nothing
cannot raise the tier [exp017]. Every decision is written to an audit log whose lines are
chained by hash, and any alert is staged for a named person to approve; in this study
nothing was sent.

## 4. Detection of the 2026 event

Replaying the archive through the live code, as a feed would have delivered it,
NK.KKN's trigger opens at 02:52:30.3 UTC and IO.EVN's at 02:52:43.1, 12.8 s later, a
difference every point in the source zone can explain [exp019, exp020]. The first windows
holding a full decision segment close at 02:55:00 at both stations, and each decides
mass movement like: an Advisory, held below Warning for want of a gauge [exp020].

On the decision segment the event's LF/HF is 4.92 on NK.KKN and 15.07 on IO.EVN, with
centroids of 1.89 and 1.53 Hz, against earthquake medians of 1.48 and 2.22 for LF/HF
and 3.11 and 2.67 Hz for the centroid [exp005, exp010].

**Lead time.** The surge reached Timure about 4 minutes after the onset, Syabrubesi
about 11 and Bidur about 38 [exp011]. At the measured decision time of about 2.6 minutes,
those leave 1.4, 8.4 and 35.4 minutes (Figure 7) [exp020]. The pipeline's speed barely
matters: across any plausible latency the warning at each town changes by about a
minute [exp011]. Timure is set by its distance from the source, and no detector can save
it. In 2026 the first warnings came about 20 minutes after the failure, after the water
had passed Syabrubesi.

## 5. How far it can be trusted

**Overlap with earthquakes.** The separation is a tendency. On NK.KKN 11 of 64
earthquakes, 17.2 percent, meet the event's own values on both features; with the
margin, 14 of 64, 21.9 percent [exp005, exp022]. On IO.EVN 6 of 132, 4.5 percent
[exp010]. The event sits further into the low frequency tail at the further station, so
the separation is a property of the source, not of one site [exp010]. The features also
track earthquake size and distance, so a classifier on them must control for both
[exp003].

**False alarms.** On the noise corpora, at the operating point, each rule's contribution
is shown in Table 1 and Figure 3 [exp027].

*Table 1. False alarms per station month, 20 percent margin.*

| Rules | NK.KKN | IO.EVN |
|---|---:|---:|
| Trigger only | 370 | 1,138 |
| + spectral | 34 | 110 |
| + catalogue | 24 | 83 |
| + H/V | 6.9 | 37 |
| + partner in the catchment | 0 | 6.1 |
| All rules, falling back to catalogue and H/V when the partner has no data | **3.4** | **15** |

The partner station does most of the work. It had no data for 3 of NK.KKN's 10 spectral
windows and 11 of IO.EVN's 36, and a window that cannot be corroborated falls back to
the other rules, so the rates to quote are 3.4 and 15, not 0 and 6.1. With counts this
small the upper limits of the 95 percent intervals are three to five times the point
values. The target set at the start of the project was 1.

**Misses.** With one event, misses cannot be counted, but they can be estimated. Scaled
copies of the 2026 waveform were added to 120 real noise windows from NK.KKN and passed
through the live decision function (Figure 2) [exp026]. Half are caught at about 2.5
percent of the 2026 amplitude and nine in ten at about 10 percent. At every size the
share detected is within a point of the share that triggered: the trigger sets the
limit, and the rules after it cost nothing on this event shape. Without the margin the
full size event is caught in 2 percent of windows.

## 6. The search for a second event, and tests elsewhere

**In the region.** Five older catalogued events were replayed through the live code:
Jure 2014, Langtang 2015, Melamchi 2021, Thame 2024 and Rasuwagadhi 2025. None produced
a mass movement like segment on either station [exp020]; none had a cross station
candidate that fit its source [exp008]. Radar confirmed none of them; Thame came closest
and failed a null test against ordinary years [exp012, exp013, exp016]. The Chamoli
avalanche, 610 km away, does not trigger the detector [exp023], although it shows faintly
between 0.05 and 0.5 Hz [exp029].

The densest data that exists was searched last. From June 2015 to May 2016 a temporary
network had twelve stations with long period channels within about 100 km of the 2026
source. A scan of 2,844 station days in 0.02 to 0.08 Hz found 1,195 events seen by at
least four stations; the catalogue explained 932. Of the 263 left, 76 were inspected in
the short period record: 50 were earthquake like, 24 had no short period arrival at all,
and none was mass movement like at two stations [exp030]. The one strong local
candidate faded the wrong way with distance, the mark of a tilting sensor. The scan would
have listed an event with one or two percent of the 2026 long period amplitude. A second
event of anything like this size did not happen in central Nepal in that year, or is
not in the open data.

**Elsewhere.** A cascade outside Nepal cannot add a second positive here, but it can test
whether the signature belongs to the source. On 23 August 2017 about three million cubic
metres of rock fell from Piz Cengalo, Switzerland, and turned into debris flows within
30 s (Walter and others, 2020). On five Swiss stations from 23 to 128 km, with the same
segment and features, the avalanche is lower in frequency than the median local
earthquake at every station, and 0 to 22 percent of 46 to 50 local earthquakes reach its
values, an overlap like NK.KKN's [exp031]. But the Nepal thresholds pass it at one station
of five, and its H/V ratio sits at the local earthquake median at every station.

On 18 October 2015 about 60 to 75 million cubic metres of rock fell from the slope at
the terminus of Tyndall Glacier into Taan Fiord, Alaska (Higman and others, 2018). On four
stations from 18 to 85 km the landslide's segment has an LF/HF of 108 to 723 and a
centroid of 0.79 to 1.14 Hz, and none of 28 to 41 local earthquakes on any of them reaches
its values [exp033]. Two stations at 127 and 135 km did not trigger on it. The Nepal
thresholds pass the landslide here, but they also pass 22 to 78 percent of the region's
earthquakes, which are low in frequency at these stations too. Its H/V ratio is below
most earthquakes' at two stations and above most at the other two.

Across the three events the separation grows with size. Bondo, the smallest at about
three million cubic metres, overlaps up to 22 percent of its region's earthquakes; Taan
Fiord, twenty or more times larger, overlaps none. Whatever its cause in Nepal, the 2026
event's H/V signature appears at neither outside event.

Taan Fiord also showed a failure a live system would meet. An M4.1 earthquake 470 km
away arrived three minutes before the landslide, below the distant earthquake screen's
magnitude, and its late waves passed the Nepal rule at three stations. A first analysis
that took the strongest trigger near the reported time measured that earthquake instead
of the landslide; only the causal rule, that nothing arrives before its own origin,
separated them [exp033].

A rule set relative to each station's own earthquakes, at the 0.80 quantile, passes six
of seven station records of the two events, where the absolute rule passes three, and
lets through 16 to 22 percent of earthquakes on every station [exp032]. On NK.KKN it is
slightly stricter on noise than the absolute rule, 27 a month against 34 at the spectral
layer. On IO.EVN it is far worse, 349 against 110, because the 2026 event stood so far
out there.

## 7. Running it live

The detector runs as a shadow service: it connects to a public SeedLink server, decides
on every window, and records each decision without sending anything. The first live day
taught two things [exp025]. Its one Advisory was an M5.2 earthquake 4,000 km away, near
Yemen, because the live loop then had no catalogue to check against; it has one now.
And five decisions that sat just under the thresholds did not exist in the archive data
at all. They came from windows closed before the last packets arrived, a bug found only
by replaying the same hours from the archive. The rule since then is that a behaviour
seen only on the live feed is replayed before it is believed.

The feed adds about 16 s on average [docs/LATENCY.md]. When a station returns from an
outage it sends hours of stored data at once; those windows are counted apart, and any
decision built from them is staged with a note that it was made late, so a lead time is
never quoted from a budget the feed did not keep.

**TO COME: the long shadow run.** Months of live operation on an always on machine, with
its decisions, its outages, and its measured false alarm rate.

## 8. Limits

* **One event.** The thresholds were set on the event they detect. The margin, the
  injection test and the outside events reduce that dependence; they do not remove it.
* **Thresholds and the H/V rule are local.** They missed Bondo at four stations of five
  [exp031] and passed most Alaskan earthquakes [exp033]. The H/V signature appears at
  neither outside event and must not be described as a general mark of mass movements.
* **One fragile station.** Kakani has gone silent for hours at a time, and the partner
  is 131 km away. There is no third open station [exp028].
* **The station's own record matters more than the trigger.** Starting the segment
  anywhere from 10 s before to 10 s after the trigger changes LF/HF by 11 percent or less
  at the Nepal and Swiss stations and changes no record's verdict [exp034]. Starting later
  makes the events look lower in frequency, but the earthquakes faster, so the first
  trigger stays the rule. Two Swiss stations at the same distance gave different answers
  at Bondo because of their records, the site or the path, not the trigger, which corrects
  the explanation first given in exp031. NK.KKN, the station the service decides on, only
  just passes a rule set on its own earthquakes, and fails it from 5 s after the trigger
  [exp034].
* **The travel times are from one flood.** The 4, 11 and 38 minutes are this event's.
  A smaller or slower surge travels differently.
* **False alarm rates rest on small counts** measured on about a third of a station
  month per station. The live run is the real test.

## 9. What would make it work

The method needs three things it does not have. First, more stations: the national
seismic network's stations near the valley would remove the dependence on one station
and give the partner rule a partner close by. Second, the river gauges as the second
independent signal, through an agreement with the hydrology department, so that a
seismic Advisory can become a Warning. Third, an operator: an agency that runs it,
approves its alerts, and owns the decision. Until then this is a research instrument
that shows the signal is there, early, and separable often enough to be worth building
on.

## Data and code availability

All code, configurations, experiment records and figures are in the project
repository; `scripts/reproduce.py` regenerates every experiment from the waveform
cache, and continuous integration reruns four of them. Waveforms are from the NK and IO
networks through EarthScope, the CH network through the Swiss Seismological Service, the
AK network through EarthScope, and the XQ temporary network. Catalogues are from USGS
ComCat and the Swiss Seismological Service. Elevation is Copernicus GLO-90; radar is
Sentinel-1.

## Figures

1. The 2026 event on NK.KKN and IO.EVN (`docs/figures/fig01_event_2026.png`).
2. Share of injected events caught, by size (`fig02_detection_curve.png`).
3. False alarms per station month as rules are added (`fig03_ablation.png`).
4. What the threshold margin costs and buys (`fig04_margin.png`).
5. Distant earthquake screening: false alarms removed against time set aside
   (`fig05_suppression.png`).
6. The 2026 radar change against the same weeks of other years (`fig06_radar_nulls.png`).
7. Warning each town would have had in 2026 (`fig07_lead_time.png`).
