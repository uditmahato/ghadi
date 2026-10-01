# Experiment 025: what did the first live day show, and what does today's code make of it?

**Question.** The shadow service ran live on NK.KKN for 20 hours on 26 and 27 September
2026 before the session that started it ended. It made ten decisions and staged one
Advisory. Replaying the same 20 hours from the archive through today's code, with the
horizontals, the partner station, and the earthquake catalogue, what changes?

**Answer.** Nothing is staged. The one Advisory is a distant earthquake and is set
aside. Five live decisions that sat just under the old thresholds do not exist in the
archive data at all: they were made by a bug in how the live loop closed its windows.

| | Live run, 26 Sep | Replay under today's code |
|---|---:|---:|
| Windows | 484 | 1,216 |
| Decisions | 10 | 20 |
| Mass movement like | 1 | 0 |
| Set aside as distant earthquakes | 0 | 4 |
| Corroborated by the partner station | not available | 6 |
| Alerts staged for a person | 1 | **0** |

Run 2026-10-01. The live records are the service's own audit log. The replay fetched
the vertical and horizontals for NK.KKN and the vertical for IO.EVN for the period.

## The Advisory was an earthquake near Yemen

At 16:40:35 UTC the station recorded a strongly low frequency arrival (LF/HF 20.9,
centroid 1.25 Hz). The catalogue has an M5.2 at 16:33:43 UTC, 35 degrees away, whose P
wave is predicted at Kakani at 16:40:42, seven seconds from the detection. Under today's
rule (exp024) it is set aside. Its horizontal to vertical ratio was 1.09, well under the
1.86 the rule now asks for, so the H/V rule would have rejected it too.

The replay also sets aside an M5.6 at 73 degrees (14:19) and an M5.0 at 49 degrees
(20:01 and 20:09). The partner station saw the Yemen and M5.6 arrivals as well:
**agreement between two stations does not protect against a distant earthquake,**
because both stations see it. Only the catalogue and the H/V rule do.

## Five decisions that were never there

The live run recorded decisions at 08:28, 08:56, 14:50, 18:43, and 18:46 with almost
identical features: LF/HF 4.63 to 4.71 and a centroid of 2.17 to 2.19 Hz, just under
the thresholds of the day. They looked like a repeating local source, and under the 20
percent margin adopted since, all five would have been staged.

The replay finds onsets at two of those times (08:56:56 and 18:46:25) and their
features are nothing like that: LF/HF 0.09 and 0.29, centroids of 9 and 12 Hz. They
are ordinary high frequency local transients. The other three have no trigger at all.

The cause was in the live loop. It judged a window overdue five seconds after its end
by the arrival clock, but the feed runs 15 to 25 seconds behind, so every window was
closed before its last packets arrived and its tail was filled with zeros. A decision
segment that ran into that tail measured the step, not the ground. Replayed data
arrives with a fixed 6 second delay in the tests, which is why no test caught it. The
fix (windows are judged overdue against the feed's own delay, and a trigger on the
edge of a filled gap is skipped) was made while wiring the partner station, before
this was understood to have affected the live run.

**Checked, not assumed.** The code the live run used (commit eb3f9c2) was replayed on the archive for 08:40 to 09:10 UTC at two feed delays. At 6 s it gives the true reading at 08:56:56, LF/HF 0.29 and 9.03 Hz. At 20 s, the delay the live feed really has, it gives LF/HF 4.65 and 2.18 Hz, the live run's value to the second decimal. A regression test now replays one trace at both delays and requires the same decision.

**What this means for the earlier numbers.** Every false alarm rate in exp018 to exp022
was computed from archive windows, not live ones, so none of them is affected. The live
run's own delay figures are unaffected too. Only its ten decisions are, and they are
kept in `results.json` as they were recorded.

## What the first live day does say

* **Feed delay:** 95th percentile 25.5 s over 484 windows, in line with the earlier
  partial log and well inside the 120 s limit.
* **No false alarm in 20 hours** once the rules are applied, on one station. That is
  0.03 station months, far too short to mean anything about the rate.
* **Decision latency:** median 158 s in the replay, the same as exp020.
* **The service must not depend on a session.** It died when the session that started
  it ended. It has been restarted as a detached process with today's code.

## Design

`scripts/run_shadow.py replay` over 2026-09-26 08:20 to 2026-09-27 04:36 UTC with the
default settings: horizontals on, IO.EVN as partner, the catalogue for the period from
the USGS service, and the suppression rule of exp024.
