# Experiment 009 — What changes when the noise corpus stops containing earthquakes?

**Question.** exp004 found that half the detector's false alarms were teleseisms the
6-degree regional exclusion never considered. Those windows are **mislabelled**: they
contain real earthquakes and are not noise. What does the corpus look like once the
exclusion covers them, and does the measured rate change?

**Answer: 27 of 388 windows were not noise. The corpus is now correctly labelled, the
rate is 6.8 per station-month — and a consistency check between two independent routes
passes exactly.**

Run 2026-09-03, `NK.KKN..BHZ`.

## The corpus was 7% earthquakes

| Status | Before | After |
|---|---:|---:|
| `ok` (usable noise) | 388 | **366** |
| `excluded_regional_event` | 7 | 7 |
| **`excluded_teleseism`** | — | **27** |
| `no_waveform` | 40 | 35 |

Examples of what was being counted as noise:

- M5.6 Anamizu, **Japan**
- M5.5 Vinchina, **Argentina**
- M5.6 Loreto, **Mexico**
- M5.6 Kokopo, **Papua New Guinea**
- M5.5 Ust-Kamchatsk, **Russia** — one of the two teleseisms exp004 identified by hand

The geographic spread is the point. These are not near-misses of the 6-degree radius;
they are the other side of the planet. Attenuation strips their high frequencies over
that distance, so they arrive low-frequency and long-duration — the mass-movement
signature, produced by different physics arriving by a different route.

## The consistency check that matters

Exclusion at corpus-construction time and suppression at detection time are two
different code paths solving the same problem. If they disagreed, the measured
false-alarm rate would describe a system nobody runs.

**Re-running exp006's runtime suppression against the corrected corpus finds zero
further teleseisms** — 0 of 108 triggering windows. Corpus exclusion removed exactly
what runtime suppression would have removed, and nothing else.

That is not automatic. It holds because both paths now call one `phase_window`
function, added in this change. Before it, the corpus excluded on a flat ±1 h guard
around the origin time while the detector suppressed on a P-to-surface window — and
exp006 established a flat guard around the origin misses teleseisms entirely, because
the arrival that trips the detector can be twenty minutes after P.

## The rate did not really improve

| | Windows | Station-months | Per station-month |
|---|---:|---:|---:|
| exp004 (mislabelled corpus) | 4 | 0.31 | 12.9 |
| exp006 (runtime suppression) | 2 | 0.31 | 6.5 |
| **exp009 (corrected corpus)** | **2** | **0.29** | **6.8** |

**6.5 and 6.8 are the same two events.** The denominator moved because the corpus lost
22 windows, not because anything got better. Quoting the change as an improvement would
be wrong: the *rate* is unchanged, and what improved is that the corpus is now labelled
correctly — which matters for training a classifier on it, not for the headline number.

Still roughly **7× over the ≤1 target**, on two events, with a Poisson 95% interval of
roughly 0.8–25. The interval remains wider than the estimate.

## The two survivors are still unexplained

| Window | LF/HF | Centroid |
|---|---:|---:|
| 2025-04-02 16:00 | 5.47 | 1.98 Hz |
| 2025-04-23 16:00 | 8.01 | 1.56 Hz |

Both well above the cascade's LF/HF of 4.14, both at 21:45 NPT, both in April. Neither
is explained by any catalogued M≥5.5 anywhere on Earth. Candidates: smaller teleseisms
below the magnitude floor, regional events absent from the catalogue, or genuine local
noise of a kind not yet characterised.

**Lowering the magnitude floor to find out would trade against over-suppression**, and
hiding a real local event is far worse than a false alarm. That trade needs measuring
before it is made, not assuming.

## What this does not change

- The corpus is still one station. IO.EVN needs its own, and rates are per station.
- The positive class is still n = 1.
- Two surviving events is not a rate.
- The corpus still under-samples August–December (13–18 windows per month against
  39–46 for January–July), which is the season the 2026 cascade occurred in.
