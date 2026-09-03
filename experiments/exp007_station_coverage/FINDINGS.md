# Experiment 007 — Can the positive class grow, and on which station?

**Question.** Everything measured so far is limited by one number: **the positive class
is n = 1**. M3's classifier is not a supervised problem at n = 1, and the handoff's
mitigation for that (risk R1) is the Gorkha co-seismic landslide population — which
the coverage map appeared to rule out, since NK.KKN's archive starts around 2020-03 and
Gorkha was April 2015.

So: is the positive class reachable at all, and if so where?

**Answer: yes, on IO.EVN. All six candidate events have waveform data there, including
Gorkha 2015 and Jure 2014, which NK.KKN cannot reach. The constraint was never the
events — it was the station.**

Run 2026-09-02.

## Which stations hold which events

A ±600 s window around each candidate event, on the four open stations in range:

| Event | NK.KKN | IO.EVN | NQ.KNSET | NQ.KTNP2 |
|---|---|---|---|---|
| Gorkha / Langtang 2015-04-25 | — | **yes** | — | — |
| Jure 2014-08-01 | — | **yes** | — | — |
| Melamchi 2021-06-15 | yes | **yes** | — | yes |
| Thame 2024-08-16 | yes | **yes** | yes | — |
| Rasuwagadhi 2025-07-08 | yes | **yes** | yes | yes |
| Bhote Koshi 2026-08-26 | yes | **yes** | yes | yes |

**IO.EVN has all six.** NK.KKN has four.

## Coverage, station by station

One 10-minute probe per month (`scripts/probe_availability.py`):

```
IO.EVN   year  JFMAMJJASOND
         2013  ............
         2014  .....#######     <- Jure (2014-08) reachable
         2015  ####.#####..     <- Gorkha (2015-04) reachable
         2016  ............
         2017  ......######
         2018  #######.#.##
         2019  #..########.
         2020  ...#########
         2021  #..###...###
         2022  ....#....#.#
         2023  ##.##.#.####
         2024  #.##########
         2025  #.####.#####     <- covers 2025-08..12, which NK.KKN lacks
         2026  ########
```

| | Months with data |
|---|---:|
| NK.KKN alone | 71 |
| IO.EVN alone | 98 |
| **Union** | **119** |
| Both | 50 |
| **IO.EVN only** | **48** |

**The union is 68% larger than NK.KKN alone**, and the two stations' gaps are largely
independent: 69 months have data on exactly one of them. IO.EVN covers 2025-08 through
2025-12 — precisely the five-month hole that made the first noise-corpus attempt return
2 usable windows from 80.

## What this changes

**Risk R1 is materially less severe than it looked.** The handoff calls the Gorkha
co-seismic landslide population "the key asset that makes this project tractable", and
an hour ago it appeared unreachable. It is reachable, on IO.EVN, with the caveats below.

**IO.EVN is not redundancy — it is the deeper archive.** The handoff lists it as a
secondary station, and the working assumption throughout this repository has been that
NK.KKN is primary because it is nearest (55.9 km against 130.9 km). For *archive* work
that assumption is backwards: IO.EVN has 38% more months and is the only station
reaching before 2020. For *real-time* work NK.KKN's proximity still matters, so the two
roles genuinely differ and the config should stop implying otherwise.

**Every corpus in this repository is smaller than it needed to be.** The 64-event
earthquake corpus and the 388-window noise corpus were both drawn from NK.KKN alone.
Re-harvesting across both stations is the single cheapest way to grow them.

## The caveats, which are not small

- **Distance.** IO.EVN is 130.9 km from the 2026 source against NK.KKN's 55.9 km.
  Signals are weaker and site response differs, so features are not interchangeable
  between stations without response deconvolution (issue 2.4, implemented) — and even
  then exp003 found magnitude confounds these features, so a station change may confound
  them too. **Any cross-station corpus needs per-station baselines**, not pooled ones.
- **A false-alarm rate is per station.** The 6.5/station-month figure is NK.KKN's.
  IO.EVN needs its own noise corpus before its rate means anything, and the two cannot
  be averaged.
- **"Has data" is not "has a detectable signal".** These events were confirmed present
  in the archive, not confirmed visible. Thame 2024 was a small GLOF ~150 km from
  IO.EVN; a non-detection there is entirely possible and would itself be informative.
- **Origin times remain coarse.** Four of the six have news-derived times with
  uncertainties of one to three hours, which is why they were excluded from the corpus
  in the first place. Waveform availability does not fix that; it makes it worth
  searching those windows, which is a separate piece of work.
- **Coverage is probed, not proven.** One window per month cannot see intra-month gaps.

## What this does not change

The positive class is still n = 1 **today**. Nothing here has yet produced a second
labelled positive window — it has established that five more are worth going after, and
where. Whether they contain usable signals is the next question, not this one's answer.
