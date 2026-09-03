# Experiment 006 — How much does teleseism suppression buy?

**Question.** exp004 found that two of four false alarms were distant earthquakes,
identified by hand on four windows. This applies the rule systematically — every trigger
in every noise window, against a global M≥5.5 catalogue of 1,133 origins — and asks what
the corrected rate is.

**Answer: the false-alarm rate halves, 12.9 → 6.5 per station-month.** Getting there
required fixing the rule, and that fix is the more useful finding.

Run 2026-09-02. 388 noise windows (0.31 station-months), cached waveforms and catalogue.

## Results

| Quantity | Count | Per station-month |
|---|---:|---:|
| Triggering windows (STA/LTA baseline) | 120 | 387.3 |
| — of which explained by a teleseism | 10 | 32.3 |
| Passing spectral criteria (exp004) | 4 | 12.9 |
| **— after teleseism suppression** | **2** | **6.5** |

| Window | LF/HF | Outcome |
|---|---:|---|
| 2024-07-07 20:00 | 19.22 | **suppressed** — M6.2 Bonin Islands at 47° |
| 2024-09-23 20:00 | 80.03 | **suppressed** — M6.0 Indonesia at 46° |
| 2025-04-02 16:00 | 5.47 | survives — unexplained |
| 2025-04-23 16:00 | 8.01 | survives — unexplained |

## The rule had to be fixed, and how it failed is the point

**The first implementation caught only one of the two.** It modelled a tolerance window
around the predicted **P** arrival, which is the obvious design and is wrong.

The Indonesia window's trigger fired at 20:10:11 — **647 s after the predicted P**, and
far outside any sane tolerance. But it fired **24 s after the Lg/S arrival** (~4.5 km/s
across 46°). Checking the phases:

| Phase | Predicted arrival |
|---|---|
| P | 19:59:23 |
| **Lg/Sn (~4.5 km/s)** | **20:09:47** ← trigger at 20:10:11 |
| Rayleigh (~3.5 km/s) | 20:15:09 |
| Slow surface (~3.0 km/s) | 20:19:10 |

**STA/LTA fires on the largest arrival, and for a distant earthquake that is never P.**
It is S, Lg, or the surface train, arriving minutes to tens of minutes later. A detector
tuned to catch emergent low-frequency energy is, if anything, *more* likely to trigger
on the surface train than on the body wave.

So suppression is not a tolerance around one phase — it is a **window from P through the
slow end of the surface train**, plus margins for travel-time model error and coda.
Rewritten that way, both teleseisms are attributed, and exp004's hand analysis is
vindicated.

**This is worth stating plainly because "just cross-check the global catalogue" sounds
trivial and is not.** The naive implementation silently under-suppresses in exactly the
cases that matter most — the large, distant, low-frequency events that most resemble the
target signal. A version of this project that had shipped the P-only rule would have
believed it had teleseism suppression while retaining most of the problem.

## Over-suppression: the risk that matters more

Suppressing a real local mass movement is far worse than a false alarm, so a rule that
explained away most triggers would be unusable regardless of what it does to the rate.

**10 of 120 triggering noise windows (8.3%) are attributed to a distant earthquake.**
That is a modest fraction: the rule is selective, not a blanket. Two structural guards
keep it that way — a magnitude floor of M5.5, below which a teleseism cannot carry
enough energy to trip a regional station, and windows that, while long, are rare: 1,133
global origins over 2.6 years is roughly 1.2 per day.

**Not yet tested: whether the rule would suppress the 26 August 2026 cascade itself.**
It should not — no global M≥5.5 has a phase window covering it — but that check has not
been run, and "the suppressor does not eat the one event we exist to detect" is exactly
the assertion that must never be assumed. It belongs in the M3 test suite as a hard
regression.

## Where the rate now stands

| Stage | Per station-month |
|---|---:|
| Target (handoff M3) | ≤ 1 |
| STA/LTA baseline | 387.3 |
| + spectral criteria | 12.9 |
| **+ teleseism suppression** | **6.5** |

Still roughly **6× over target**, on two surviving events, with a Poisson 95% interval
of roughly 0.8–23 per station-month. The interval remains wider than the estimate, and
0.31 station-months cannot resolve that.

The remaining designed mechanism is corroboration: an independent downstream gauge
anomaly before a WARNING (`ghadi.fusion`). It stays unmeasurable while blocker B2 is
open, and it is now carrying the whole remaining gap.

## What this experiment cannot show

- **Two surviving false alarms is not a rate.** It is two events.
- The two unexplained windows have LF/HF 5.47 and 8.01 — well above the cascade's 4.14.
  They may be smaller teleseisms below the M5.5 floor, regional events absent from the
  catalogue, or genuine local noise. They were not investigated individually, and
  lowering the magnitude floor to find out would trade against over-suppression.
- Suppression was applied to noise only. Its effect on the earthquake corpus, and its
  behaviour on the positive event, are untested.
