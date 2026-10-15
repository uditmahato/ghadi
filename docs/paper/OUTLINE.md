# Paper plan

The working plan for the first paper from this project. It names the claim, the
evidence for each part, and what is still missing. Every number here comes from an
experiment in this repository; the experiment is named next to it so it can be checked
and rerun.

## Title

**Detecting river blocking mass movements with open seismic stations: the 26 August 2026
Bhote Koshi flood surge**

Subtitle, if the journal allows one: *what a single event can and cannot tell us about
flood warning*

## Research question

Can open seismic stations detect a mass movement that blocks a Himalayan river soon
enough to warn people downstream, and how far can that detection be trusted when only
one such event has been recorded?

## Target journal

First choice **Natural Hazards and Earth System Sciences** (open access, takes case
studies with a warning angle, open review). Second choice **Seismological Research
Letters**. The code can go separately to the **Journal of Open Source Software**.

## Draft abstract

On 26 August 2026 an ice and rock avalanche in the Lhende Khola blocked and then
released the Bhote Koshi, sending a surge down the Trishuli that left more than a
thousand people dead. The surge destroyed four of five downstream river gauges before
their thresholds triggered. We ask whether open seismic stations could have given
warning instead. The mass movement was recorded by the one open broadband station in
Nepal, 56 km away, and by a station in India 131 km away. Its signal is richer in low
frequencies than that of 64 regional earthquakes on both stations, but the separation
is a tendency, not a boundary: with the safety margin the detector uses, 14 of the 64
earthquakes pass the spectral rule. A detector built on spectral shape, the ratio of horizontal to vertical energy,
the screening of distant earthquakes against a live catalogue, and agreement between
the two stations flags the event about 2.5 minutes after the slope failed. With a
measured decision delay of about 160 s that leaves roughly 35 minutes of warning at
Bidur and 8 at Syabrubesi, while Timure, 4 minutes downstream, cannot be warned by any
detector. Counting the times the second station is missing, the system raises about 3
false alarms per station month at the Nepal station and 15 at the Indian one. Injected
copies of the 2026 signal are caught half the time at 2.5 percent of its amplitude. The
2017 Piz Cengalo rock avalanche in Switzerland shows the same low frequency tendency
against its own region's earthquakes on five stations, but the Nepal thresholds pass it
at only one, so the operating rule is local while the signature is not. A
search of catalogued events, satellite radar, a neighbouring range, and a year of dense
network data from 2015 to 2016 found no second event of this kind, so every estimate
rests on one positive case. We release the code, the data and a shadow service that
runs the detector live without sending alerts, and argue that the method is ready to be
tested on national network data, not to be relied on by itself.

> Numbers to update before submission: the live running time, any false alarm the live
> service records, and the decision delay measured over the long run.

## Outline

| Section | What it says | Evidence |
|---|---|---|
| 1. Introduction | Cascading flood surges in the Himalaya (Chamoli 2021, Melamchi 2021, Bhote Koshi 2026). Gauges get destroyed; the ground shakes before the water arrives. Prior work showed regional networks can see such events after the fact. The gap: an open, live, honestly measured detector | Literature below |
| 2. The event and the data | The 2026 cascade; NK.KKN at 56 km, IO.EVN at 131 km; catalogue; radar confirmation of the source | exp001, exp007, exp010, exp012, exp013, fig01, fig06 |
| 3. Method | Trigger, decision segment, spectral and H/V rules with a 20 percent margin, distant earthquake screening, two station agreement inside the catchment, fusion and the human gate | exp002, exp005, exp006, exp021, exp022, exp024, `docs/ARCHITECTURE.md` |
| 4. Detection of the 2026 event | When each station decides; lead time per town; why Timure cannot be saved | exp011, exp020 |
| 5. How far it can be trusted | Earthquake overlap; false alarm rates per station; what each rule adds; smallest event caught | exp003, exp004, exp009, exp018, exp019, exp026, exp027, fig02, fig03, fig04, fig05 |
| 6. The search for a second event, and a test elsewhere | Catalogued events, radar, Chamoli, the 2015 to 2016 network scan; why the positive class stays at one. Then Bondo 2017: the signature appears on another range and network, the thresholds and H/V rule do not carry over | exp008, exp016, exp023, exp029, exp030, exp031, exp032, exp033, exp034 |
| 7. Running it live | The first live day and the bug it exposed; feed delay; backlog handling; the long shadow run | exp025, the shadow run (to come) |
| 8. Limits | n = 1; thresholds shaped on the event they detect; one fragile station; no third open station | exp028, every FINDINGS limits section |
| 9. What would make it work | National network data, river gauges as the second signal, operation by an agency | `docs/outreach` |
| Data and code | Repository, release bundle, reproduce script | `scripts/reproduce.py`, `docs/RELEASE.md` |

## The claims, and how strong each one is

| Claim | Strength | Why |
|---|---|---|
| The 2026 event is visible and early on open stations | Strong | Two stations, radar confirms the source |
| Its spectrum differs from most earthquakes | Moderate | 64 earthquakes, but 14 overlap |
| The detector would have flagged it about 2.5 minutes after onset | Strong for this event | Replayed on archive data and through the live code |
| About 35 minutes of warning at Bidur | Moderate | One calibrated travel record |
| False alarm rates | Moderate | Measured on archive noise; the live run will test them |
| It would catch a smaller event | Weak | Injection of one event shape only |
| The low frequency signature is a property of this kind of source | Moderate to strong | Two Nepal stations, five Swiss stations on Bondo (exp031), four Alaskan stations on Taan Fiord, where no earthquake reaches it (exp033) |
| The thresholds and the H/V rule work elsewhere | Shown false | The Nepal rule passes Bondo at one station of five (exp031) and passes most Alaskan earthquakes (exp033); H/V is not distinctive at either |
| A rule set from each station's own earthquakes would carry to a new network | Moderate | 6 of 7 station records at the 0.80 quantile, same earthquake share, but three times IO.EVN's noise alarms (exp032) |
| It would catch a different kind of event in Nepal | Not shown | n = 1. Say so plainly |

## Reading list

The closest work comes first. Check each reference against the journal page before
citing it; the ones marked **check** were written from memory and need their details
confirmed.

| Reference | Why it matters | Status |
|---|---|---|
| Cook, Rekapalli, Dietze and others (2021). Detection and potential early warning of catastrophic flow events with regional seismic networks. *Science* 374, 87 to 92 | The closest prior work: Chamoli 2021 seen on a regional network, with early warning proposed. This paper must say clearly what it adds: a live, open, single station system with measured false alarms | check |
| Cook, Andermann, Gimbert, Adhikari and Hovius (2018). Glacial lake outburst floods as drivers of fluvial erosion in the Himalaya. *Science* 362, 53 to 57 | The 2016 outburst flood in the same Bhote Koshi valley, recorded by seismic stations along the river | check |
| Burtin, Bollinger, Vergne, Cattin and Nábělek (2008). Spectral analysis of seismic noise induced by rivers. *Journal of Geophysical Research* 113, B05301 | River noise on the Trishuli recorded by seismometers; background for what the stations hear | check |
| Shugar and others (2021). A massive rock and ice avalanche caused the 2021 disaster at Chamoli, Indian Himalaya. *Science* 373, 300 to 306 | The best documented comparable cascade | check |
| Ekström and Stark (2013). Simple scaling of catastrophic landslide dynamics. *Science* 339, 1416 to 1419 | Large landslides produce strong long period signals; supports exp029 and exp030 | check |
| Hibert, Ekström and Stark (2014). Dynamics of the Bingham Canyon Mine landslides from seismic signal analysis. *Geophysical Research Letters* 41 | Seismic analysis of landslide dynamics | check |
| Chmiel, Walter and others (2021). Machine learning improves debris flow warning. *Geophysical Research Letters* 48 | Seismic debris flow warning in an instrumented catchment; the dense network contrast | check |
| Walter and others (2019 or 2020; other papers cite it both ways). Direct observations of a three million cubic meter rock slope collapse with almost immediate initiation of ensuing debris flows. *Geophysical Research Letters* 47 | Bondo 2017, a well recorded cascade outside the Himalaya | check |
| Allen (1978). Automatic earthquake recognition and timing from single traces. *Bulletin of the Seismological Society of America* 68, 1521 to 1532 | The STA/LTA trigger | check |
| Nakamura (1989). A method for dynamic characteristics estimation of subsurface using microtremor on the ground surface. *Quarterly Report of RTRI* 30 | The H/V ratio | check |
| Sattar and others (2025). The Sikkim flood of October 2023. *Science* | South Lhonak outburst, a recent transboundary cascade | check |
| Chen and others (2025), Erosional cascade during the 2021 Melamchi flood, *Nature Geoscience* 18 | Melamchi for the introduction | confirmed |
| USGS and WMO accounts of the 2026 event | Already listed in `data/catalog/NPL-2026-08-26-BHOTEKOSHI-001.yaml` | have |

## What is still missing before submission

1. **The long shadow run.** At least two months on the cloud machine
   ([DEPLOY_AWS.md](../DEPLOY_AWS.md)), so section 7 reports live false alarms and delay,
   not only archive ones.
2. **Testing on events elsewhere.** Bondo 2017 (exp031) and Taan Fiord 2015 (exp033) are
   done. It
   does not raise the Nepal count above one, and the paper must not say it does. The rule
   set relative to each station's own earthquakes is tested (exp032).
3. **The reading list confirmed** (done, see [REFERENCES.md](REFERENCES.md)) and the
   introduction written against Cook and others (2021) (done in the draft).
4. **A coauthor from the region or the field.** Someone who knows the valley or works on
   seismic hazard detection. It strengthens the paper and opens the door to data.
5. **Figures for sections 4 and 7**: a lead time figure per town and a live run timeline.
