# Experiment 033: a second mass movement outside Nepal, Taan Fiord, Alaska

**Question.** exp031 tested the method on Bondo 2017, about three million cubic metres.
On 18 October 2015 (the evening of 17 October, local time) about 60 to 75 million cubic
metres of rock fell from the slope at the terminus of Tyndall Glacier into Taan Fiord,
Alaska, and raised a tsunami that ran up 193 m (Higman and others, 2018). Nobody saw it;
it was found from its seismic signal. What does the project's method make of a much
larger event, recorded by a dense network?

**Answer.** It stands out completely at every station that triggered on it. On four
stations from 18 to 85 km, the landslide's segment has an LF/HF of 108 to 723 and a
centroid of 0.79 to 1.14 Hz, and **none of 28 to 41 local earthquakes on any of them
reaches its values on either feature**. The Nepal rule passes it at all four. But the
same rule also passes 22 to 78 percent of Alaska's earthquakes, because they are low in
frequency at these stations too, so the absolute thresholds would be useless there.
Two stations at 127 and 135 km did not trigger on the landslide at all. And an
unrelated earthquake three minutes earlier nearly corrupted the result; see below.

Run 2026-10-14. Waveforms from the AK network through EarthScope; catalogue from USGS;
both cached.

## Results

The 120 s decision segment from the onset, as in exp031. The onset is the first trigger
between the catalogue origin (05:18:26 UTC, the USGS "other event") and 240 s after it.
The comparison population is the 50 largest catalogued earthquakes of M5.5 or less within
1.5 degrees, 2013 to 2018 (M3.4 to M5.1), each measured the same way on the same station.

| Station | Distance | Onset (UTC) | LF/HF | Centroid | H/V | Nepal rule | Earthquakes reaching both values |
|---|---:|---|---:|---:|---:|---|---:|
| AK.SAMH | 18 km | 05:19:05.1 | 723 | 0.79 Hz | 2.11 | pass | **0 of 38** |
| AK.PIN | 47 km | 05:19:30.6 | 131 | 1.14 Hz | 4.17 | pass | **0 of 41** |
| AK.BAGL | 65 km | 05:19:22.0 | 255 | 1.03 Hz | 2.26 | pass | **0 of 28** |
| AK.BCP | 85 km | 05:19:51.5 | 108 | 0.93 Hz | 2.36 | pass | **0 of 35** |
| AK.CRQ | 127 km | no trigger after the origin | | | | | |
| AK.PTPK | 135 km | no trigger after the origin | | | | | |

| Station | Earthquake median LF/HF | Highest earthquake LF/HF | Earthquake median centroid | Lowest earthquake centroid | Earthquakes passing the Nepal rule | Earthquakes with H/V at or above the landslide's |
|---|---:|---:|---:|---:|---:|---:|
| AK.SAMH | 7.0 | 83 | 1.80 Hz | 1.08 Hz | 29 of 38 | 35 of 38 |
| AK.PIN | 2.2 | 23 | 2.65 Hz | 1.40 Hz | 9 of 41 | 11 of 41 |
| AK.BAGL | 9.0 | 27 | 1.88 Hz | 1.41 Hz | 17 of 28 | 5 of 28 |
| AK.BCP | 1.9 | 32 | 2.80 Hz | 1.23 Hz | 10 of 35 | 35 of 35 |
| AK.CRQ | | 35 | | 1.33 Hz | 21 of 27 | |
| AK.PTPK | | 34 | | 1.42 Hz | 21 of 41 | |

## The earthquake that nearly corrupted this

An M4.1 earthquake struck at 05:15:30 UTC, 55 km north east of Chase, Alaska, about
470 km west north west of the fjord, at 67 km depth. Its waves sweep across the network
from 05:16:24, the far western stations first. The first run of this experiment took
the strongest trigger from 60 s before the catalogue origin, as exp031 did for Bondo,
and at three stations that was a trigger from 05:17:33 to 05:18:02: almost certainly the
later waves of that earthquake, which arrive in that order across the network. The run
reported the Nepal rule passing at four stations, and it was measuring an earthquake at
three of them.

The fix is the rule the project already applies to earthquakes (`ghadi.detect.onset`):
nothing arrives before its own origin. Taking the first trigger after the catalogue
origin, the nearest station triggers first and the furthest last, 17 to 46 s
later, as one source near the fjord would give, and the landslide's own segments are lower in frequency still than the contaminated ones.

Two lessons:

* **For experiments:** an outside event's onset is the first trigger after its origin,
  and the minutes before it are checked for other earthquakes. Bondo was checked the
  same way after the fact: no earthquake of M4 or more anywhere in the world between
  07:10 and 07:40 UTC that day, and its onsets come in order of distance (exp031).
* **For operation:** a live detector in Alaska would have decided first on the M4.1's
  late waves, three minutes before the landslide. An M4.1 at 470 km is below the
  project's distant earthquake screen (M5.0 within 80 degrees), and its late waves
  passed the Nepal rule at three stations. This is the regional earthquake overlap the
  project has measured since exp003, seen from the other side, and a reason the partner
  and location rules exist.

## What it shows

* **The low frequency signature is strongest for the largest event.** Bondo, about
  three million cubic metres, sat in the tail of its region's earthquakes with up to 22
  percent overlap (exp031). Taan Fiord, twenty or more times larger, sits beyond every
  earthquake at every station that triggered. The 2026 event sat between them (17.2
  percent on NK.KKN, 4.5 percent on IO.EVN). Size, as well as source type, sets how
  cleanly the signature separates.
* **The absolute Nepal thresholds do not carry over, from either side.** At Bondo they
  missed the event at four stations of five. In Alaska they catch the landslide but also
  a fifth to three quarters of ordinary earthquakes. Relative to each station's own
  earthquakes, as exp032 proposed, the landslide passes at any quantile at all four
  stations.
* **The H/V rule does not carry over either.** The landslide's H/V is below most
  earthquakes' at two stations and above most at the other two. Together with Bondo this is strong
  evidence that the 2026 H/V signature was a property of the Nepal sites or of that
  event, not of mass movements in general.
* **A huge event can still fail to trigger at 130 km.** Both far stations had triggered
  on the M4.1 just before, at an STA/LTA of about 11, but not on the landslide. Whether
  the earthquake's coda held their long averages up, or the landslide's energy above
  0.5 Hz had faded by then, this run cannot tell. The 2026 event did trigger IO.EVN at
  131 km.

## What it does not show

* **It is not a Nepal positive.** The Nepal count stays at one.
* **The landslide's true start is uncertain.** The USGS origin comes from an automatic
  location (ML 1.4, a poor size estimate for this kind of source). Published seismic
  studies plot from 05:17 UTC. If the slide began before 05:18:26, its first minute is
  mixed with the M4.1's coda and the segments here start late in the event. They are
  still the earliest segments a causal detector could have used.
* **The comparison earthquakes are mostly small and local**, as at Bondo.

## Design

`run.py` is exp031's method with the Alaska settings: the AK network's `BH?` channels
through EarthScope, the USGS catalogue as plain CSV (ObsPy's client failed the service's
handshake repeatedly), the first trigger 0 to 240 s after the catalogue origin for the
landslide, and `ghadi.detect.pick_onset` for the earthquakes. Records whose sampling rate
is a few millionths off nominal are snapped to it before merging; a window that still
cannot be merged is skipped.
