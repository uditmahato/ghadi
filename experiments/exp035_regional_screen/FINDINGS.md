# Experiment 035: would a lower regional earthquake screen remove the live false alarms?

**Question.** In its first fortnight on the live NK.KKN feed (2 to 18 November 2026) the
shadow service staged 16 Advisories, about 31 a month against a goal of 1. Six were
distant M5.0 to M5.2 earthquakes that the current screen explains. A check on 18
November found that six of the other ten fit regional M4.4 to M4.9 earthquakes 4 to 16
degrees away, below the screen's M5.0. Would a lower regional screen, for example M4.4
and above within 20 degrees, remove them? What does it cost in time with the seismic
channel set aside? And would it ever have hidden the one positive, the 26 August 2026
Bhote Koshi event?

**Answer.** It would explain them, but only after the alert has gone out, and as
first proposed it would also have explained away the 2026 event.

* **It explains about half the regional ones.** M4.4 within 20 degrees explains 4 of
  the 8 live Advisories whose times are known (the two Xizang-Qinghai earthquakes, the
  Tajikistan M4.4 and the Afghanistan M4.9), and 3 of NK.KKN's 4 noise false alarms
  from exp018 against 0.4 expected by chance. It costs little: the channel is set aside
  9.1 percent of 2025 instead of 8.4 percent.
* **It cannot act in time.** USGS published none of 395 regional origins (M4.0 and
  above within 30 degrees, August to November 2026) before NK.KKN would have decided on
  them. M5.0 and above came in 17 minutes in the median. M4.4 to M4.6 took 6 hours in
  the median, and only a third arrived within the live feed's two hour look back. So
  the screen cannot stop any of these Advisories being staged. It can only attach an
  explanation afterwards, as the service already does for the distant ones.
* **Unguarded, it is disqualified.** USGS first published the 2026 event at 03:33:31
  UTC, 38.5 minutes after the decision, as an **M4.4 earthquake** 0.78 degrees from
  NK.KKN. Every setting at M4.4 or M4.0 would have taken that origin, and with the
  fetch threshold lowered to match, the live service would have attached "explained by
  an M4.4 earthquake" to the one real Advisory, inside the two hour look back. A screen that does that to the one positive
  must not be used.
* **The current screen has the same flaw, more slowly.** USGS now lists the event as an
  M5.2 *landslide*, and EMSC lists it as M5.2 too. The live parser ignores the event
  type, so M5.0 within 80 degrees, today's rule, explains the event with the catalogue
  as it stands. It was revised 13 hours after the event, too late for the live look
  back, but any replay with today's catalogue, or a larger event first published at
  M5.0 or above, would hide it.
* **A guard removes the danger and costs nearly nothing.** Using earthquakes only, and
  nothing within 144 km of the 2026 source zone (the catchment above Bidur plus 50 km),
  no setting hides the 2026 event. Each setting still explains exactly what it did
  before. In 2025 the guard leaves 7 M4.0 and above origins unscreened, one of them
  M5.0 or above.

No setting would have set the channel aside at the 2026 onset: nothing was published
until 38.5 minutes after the decision, and no other catalogued origin has a phase
window over either station's onset.

Run 2026-11-18. USGS catalogue and publication history, and EMSC for the live
fortnight, fetched once and cached beside `run.py`.

## Results

Each setting keeps the live screen (M5.5 and above anywhere, M5.0 and above within 80
degrees) and adds a regional tier. "Set aside" is the share of the time inside a phase
window of an origin the setting counts. The live columns cover the 8 of 16 Advisories
whose times this experiment had (see "What it does not show"). The noise columns give
false alarm windows removed (every passing segment explained), with the number expected
by chance from the set aside share in brackets. The last column says whether the
setting explains the 2026 event through its first published origin.

### NK.KKN

| Regional tier | Set aside, 2025 | Set aside, live fortnight | Live explained, catalogue now | In operation, 2 h look back | 7 day look back | With EMSC added | exp018 (of 4) | exp022, 20% margin (of 10) | exp022 with H/V (of 3) | Hides 2026 event |
|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| none (live screen) | 8.4% | 6.3% | 0 | 0 | 0 | 1 | 1 (0.3) | 3 (0.8) | 1 (0.3) | no |
| M4.0 within 10° | 8.7% | 6.6% | 2 | 1 | 2 | 4 | 1 (0.3) | 3 (0.9) | 1 (0.3) | **yes** |
| M4.0 within 15° | 9.3% | 7.0% | 4 | 3 | 4 | 6 | 2 (0.4) | 4 (0.9) | 1 (0.3) | **yes** |
| M4.0 within 20° | 9.8% | 7.5% | 4 | 3 | 4 | 6 | 3 (0.4) | 5 (1.0) | 1 (0.3) | **yes** |
| M4.0 within 30° | 10.8% | 7.8% | 4 | 3 | 4 | 6 | 3 (0.4) | 5 (1.1) | 1 (0.3) | **yes** |
| M4.4 within 10° | 8.5% | 6.5% | 2 | 1 | 2 | 4 | 1 (0.3) | 3 (0.9) | 1 (0.3) | **yes** |
| M4.4 within 15° | 8.8% | 6.7% | 4 | 3 | 4 | 6 | 2 (0.4) | 4 (0.9) | 1 (0.3) | **yes** |
| **M4.4 within 20°** | **9.1%** | **7.1%** | **4** | **3** | **4** | **6** | **3 (0.4)** | **5 (0.9)** | **1 (0.3)** | **yes** |
| M4.4 within 30° | 9.5% | 7.4% | 4 | 3 | 4 | 6 | 3 (0.4) | 5 (1.0) | 1 (0.3) | **yes** |
| M4.7 within 10° | 8.5% | 6.4% | 1 | 1 | 1 | 2 | 1 (0.3) | 3 (0.8) | 1 (0.3) | no |
| M4.7 within 15° | 8.5% | 6.4% | 2 | 2 | 2 | 3 | 2 (0.3) | 4 (0.9) | 1 (0.3) | no |
| M4.7 within 20° | 8.6% | 6.5% | 2 | 2 | 2 | 3 | 3 (0.3) | 5 (0.9) | 1 (0.3) | no |
| M4.7 within 30° | 8.7% | 6.5% | 2 | 2 | 2 | 3 | 3 (0.3) | 5 (0.9) | 1 (0.3) | no |
| M5.0 within 10° to 30° | 8.4% | 6.3% | 0 | 0 | 0 | 1 | 1 (0.3) | 3 (0.8) | 1 (0.3) | no |

M5.0 within 30 degrees or less adds nothing, because the live screen already takes M5.0
to 80 degrees. "In operation" counts an Advisory only when the explaining origin's first
USGS version arrived within the look back and at or above the fetch threshold the
setting needs (M4.4 for an M4.4 tier; the live feed fetches M4.5 and above today).

**The guarded variant** (earthquakes only, nothing within 144 km of the 2026 source zone,
on every tier) gives the same numbers in every column to within 0.1 point of set aside
time, and "no" in the last column for every setting, the live screen included.

### IO.EVN

| Regional tier | Set aside, 2025 | exp018 (of 29) | exp022, 20% margin (of 36) | exp022 with H/V (of 13) |
|---|---:|---|---|---|
| none (live screen) | 8.4% | 9 (2.4) | 9 (3.0) | 1 (1.1) |
| M4.0 within 20° | 9.9% | 10 (2.9) | 11 (3.6) | 2 (1.3) |
| M4.0 within 30° | 10.6% | 11 (3.1) | 12 (3.8) | 3 (1.4) |
| M4.4 within 20° | 9.1% | 9 (2.6) | 10 (3.3) | 1 (1.2) |
| M4.4 within 30° | 9.4% | 10 (2.7) | 11 (3.4) | 2 (1.2) |
| M4.7 within 30° | 8.7% | 10 (2.5) | 10 (3.1) | 2 (1.1) |

Every setting is in `results.json`. At IO.EVN the regional tier adds at most three
windows, near what chance gives. Its false alarms are mostly something else.

### The live Advisories, one by one

| Advisory | Time used | Check of 18 November | Live screen | M4.4 within 20° | Reaches the live feed | With EMSC |
|---|---|---|---|---|---|---|
| f2dc21c114fb | trigger 2 Nov 15:37:20 | M4.7 Xizang-Qinghai, confirmed | no | M4.7 us7000tuxi, 8.6° | yes, 49 min | yes |
| 9fa4b8c7c1c7 | trigger 2 Nov 20:57:02 | M4.5 same area, confirmed | no | M4.5 us7000tuzz, 8.6° | **no, published after 72 h** | yes |
| 1872091fcf8e | trigger 3 Nov 20:39:30 | unexplained | no | no | | no |
| a0f7dc64d0e1 | staged 8 Nov 09:01:26 | unexplained | no | no | | no |
| 63233343367b | staged 9 Nov 10:42:25 | M4.4 Tajikistan | no | M4.4 us7000tx3a, 14.4° | yes, 107 min, needs fetch at M4.4 | yes |
| 9a5c5f35d62a | staged 14 Nov 03:53:27 | M4.5 central India (EMSC) | no | **not in USGS** | | yes, M4.5 |
| e63638fbf4db | staged 15 Nov 21:46:19 | M4.4 Nepal-India or M4.9 Afghanistan | no | M4.9 us7000tyga, 14.9° | yes, 11 min | yes |
| 0ed3a703d0e9 | staged 18 Nov 00:56:24 | M4.7 Tajikistan (EMSC) | no | **not in USGS** | | yes, now mb 5.3 |

Where only the staged time was available, the trigger was taken as 156 s earlier, and
each USGS match holds for any trigger from 126 to 186 s before staging (exp020's
range). The two EMSC matches were checked at 156 s only. USGS lists no origin of M4.0
or above within 32 degrees for the central India or the 18 November Tajikistan events;
EMSC has them from GFZ and GSRAS. Under the live screen with EMSC added, the Tajikistan
event (now mb 5.3) is already explained.

### When USGS publishes regional origins

All 395 USGS origins of M4.0 and above within 30 degrees of NK.KKN from 1 August to 18
November 2026. "Published" is the earliest origin product in the event's USGS history.
"Before the decision" means before the predicted P arrival at NK.KKN plus 156 s, when
the live path would have decided.

| Final magnitude | Origins | Median delay | 90th percentile | Before the decision | Within 2 h (live look back) | Within 7 days |
|---|---:|---:|---:|---:|---:|---:|
| M4.0 to 4.3 | 159 | 6.9 days | 23 days | 0 | 34 (21%) | 82 (52%) |
| M4.4 to 4.6 | 152 | 6.1 hours | 22 days | 0 | 48 (32%) | 98 (64%) |
| M4.7 to 4.9 | 41 | 29 min | 13 days | 0 | 26 (63%) | 35 (85%) |
| M5.0 and above | 43 | 17 min | 22 min | 0 | 42 (98%) | 42 (98%) |

### The 2026 event in the catalogues

| Source | Published | Origin time | Place | Magnitude | Type | Distance from NK.KKN |
|---|---|---|---|---:|---|---:|
| USGS us7000tbwb, first version | 26 Aug 03:33:31 | 02:52:47.5 | 28.550 N 85.538 E | 4.4 mb | earthquake | 0.78° |
| USGS us7000tbwb, now (since 26 Aug 15:59) | 26 Aug 15:59:03 | 02:52:10 | 28.271 N 85.515 E | 5.2 Ms | landslide | 0.55° |
| EMSC 20260826_0000052, now | not given | 02:52:44.6 | 28.271 N 85.515 E | 5.2 Ms | "kl" (not "ke", earthquake) | 0.52° |

The decision was at 02:55:00 (exp020). The first USGS origin came 38.5 minutes later,
with an origin time 17 s after NK.KKN's onset at 02:52:30.3. Its phase window at
NK.KKN runs from 02:51:31 to 02:57:16, so it covers both stations' onsets.

## What it shows

* **The regional earthquakes are real causes of false alarms.** Under M4.4 within 20
  degrees, three of NK.KKN's four exp018 noise false alarms fall in regional windows,
  against 0.4 expected by chance, and so do four of the eight timed live Advisories. The
  18 November check was right about what they are.
* **A lower screen does not lower the alert rate.** It changes how an alert is labelled
  an hour or a day later, not whether it is staged. Even counting labelled alerts as
  handled, M4.4 within 20 degrees takes the 16 Advisories from 6 explained to 9 in
  operation (10 with a seven day look back). That leaves 6 or 7 in 0.52 station months,
  12 to 13 a month, against a goal of 1.
* **The catalogue cannot tell this system's target from an earthquake.** The first
  report of the 2026 event was an M4.4 earthquake in exactly the place the system
  watches. Any catalogue screen that reaches the catchment will, sooner or later,
  explain away the event it exists to catch. This holds for the live screen too: its
  M5.0 tier reaches 80 degrees and so the catchment.
* **The guard is nearly free.** Earthquakes only, plus 144 km around the source zone,
  changes no count in any table and leaves 7 origins of M4.0 and above a year inside
  the protected area (2025, one of M5.0 or above). A 2 degree ring was tried first and
  rejected: it took in the 2025 Tingri aftershock zone, 116 origins, 15 of them M5.0 or
  above.
* **USGS alone misses some of the regional events.** Two of the six regional matches
  are only in EMSC. With EMSC added, M4.4 within 20 degrees explains 6 of the 8.

## What it does not show

* **Only 8 of the 16 live Advisories had times.** The shadow machine's audit log was not
  available to this experiment. The 6 distant ones are explained by the live screen on
  the live record, and every setting keeps that screen, so they stay explained. The two
  weak teleseismic matches (0584f9419052, 9acc43bdf571) were not tested. Five of the
  eight times are the staged time less 156 s, not the trigger.
* **The noise counts use today's catalogue.** Magnitudes are as revised, not as first
  published, and the noise windows (2024 to 2025) have no publication history, so they
  say what a screen would explain eventually, not in operation.
* **"Published" is the earliest origin product USGS still holds.** A version withdrawn
  or merged into another event would not show. EMSC gives no publication time at all,
  so the EMSC column says nothing about speed.
* **One positive.** The 2026 event is the only case of a mass movement being catalogued
  as an earthquake that this experiment can see. The guard's 144 km is set from this
  one catchment and one location error (33 km); a different basin needs its own.
* **No waveforms were read.** Whether a regional earthquake really caused a given alarm
  is judged by timing only, except where the 18 November check looked at the signal.

## What this means for the project

Nothing in the live service changes in this experiment. For the user to decide:

* **Guard the live screen first, whatever else is chosen.** Use only origins of type
  earthquake, and let no origin within 144 km of the 2026 source zone set the channel
  aside or explain an alert. Today's M5.0 within 80 degrees tier already reaches the
  catchment, and a replay with today's catalogue would hide the 2026 event. The same
  check belongs in any experiment or replay that applies the screen to the 2026 event.
* **Then, if wanted, M4.4 within 15 or 20 degrees, guarded.** Both explain the same 4 of
  8 live Advisories; 20 degrees removes one more NK.KKN noise window for 0.3 points more
  time. It needs the fetch threshold lowered from M4.5 to M4.4 (one of the four was
  first published at M4.4). It labels alerts afterwards and does not stop them.
* **A longer look back for after the fact explanations** (days, not two hours) would
  catch the Xizang M4.5 published three days later, and a second catalogue (EMSC)
  would catch the two events USGS does not list. Both are labels only.
* **The alert rate has to come down by other means.** The two station rule (exp019,
  exp022) is the measured route, and needs a live partner station, which IO.EVN cannot
  yet be in real time.

## Design

`run.py` fetches the USGS catalogue for 2024-01-01 to 2026-11-19 (M4.0 and above within
32 degrees of NK.KKN, and M5.0 and above everywhere, every event type, as the live
parser reads it), the USGS event history with superseded products for each origin of
M4.0 and above within 30 degrees from 1 August 2026 and for us7000tbwb, and EMSC origins
of M4.0 and above within 32 degrees for 2 to 18 November 2026 and for 00:00 to 06:00 on
26 August 2026. All three are cached beside the script (`catalogue_regional_m40.json`,
`catalogue_global_m50.json`, `publication.json`, `catalogue_emsc_live.json`), and later
runs need no network.

A setting counts an origin when `ghadi.teleseism.magnitude_applies` accepts it under the
live screen (`ghadi.config.SuppressionConfig`) or under the regional tier alone
(minimum magnitude infinite, near magnitude and distance from the sweep). A time is
explained when `ghadi.teleseism.explain` finds an origin under either; time set aside
is the union of `phase_window` spans over the period, with exp024's `covered_fraction`.
Noise windows come from exp018 (zero margin) and exp022 (the live 20 percent margin,
with and without the H/V rule, H/V required where measured); a window counts as
removed only when every passing segment in it is explained. The 2026 onsets are
exp019's. The guarded variant drops every origin whose type is not earthquake, and
every origin within 144.1 km of 28.255 N 85.520 E: the farthest point of the catchment
above Bidur (`ghadi.basin.load_basin`) from that point, 94.1 km, plus 50 km.
