# Experiment 005 — Is the separation an artefact of window length?

**The worry.** Every feature to this point was computed over a fixed 2100 s window. The
cascade fills such a window — its energy persists more than 25 minutes — while a
regional earthquake occupies two or three minutes and the rest is background. If NK.KKN's
background is higher-frequency than an earthquake, that mixture would drag earthquakes
toward high frequency and manufacture separation the sources do not have.

**Answer: the worry was directionally correct and quantitatively small. The separation
is not a window-length artefact, but exp003's figure was mildly optimistic.**

Run 2026-09-02, 120 s segments from the picked onset, cached waveforms only.

## Results

| | LF/HF | Centroid (Hz) |
|---|---:|---:|
| Cascade, whole window | 4.14 | 2.04 |
| **Cascade, 120 s segment** | **4.92** | **1.89** |
| **Pre-event background** | **0.66** | **5.03** |
| Earthquakes (n=64), whole window — median | 1.48 | 3.11 |
| Earthquakes (n=64), 120 s segment — median | 1.66 | 3.04 |

Overlap with the cascade, each class measured the same way:

| Measurement | Earthquakes meeting both criteria |
|---|---|
| Whole window (exp003) | 8 / 64 (12.5%) |
| **120 s segment** | **11 / 64 (17.2%)** |

## Reading

**The background is high-frequency, as suspected** — LF/HF 0.66, centroid 5.03 Hz,
further from the cascade than any earthquake in the corpus. So dilution by background
does push a short event's whole-window spectra away from the cascade, exactly the
mechanism the worry described.

**But energy dominates duration, so the effect is small.** An earthquake occupying 10% of
a window still contributes most of that window's energy, because a power spectrum is
energy-weighted and the arrival is orders of magnitude above background. Earthquake
medians barely move between the two measurements (1.48 → 1.66, 3.11 → 3.04). The cascade
moves more (4.14 → 4.92, 2.04 → 1.89) because on a segment it is measured at its
strongest rather than averaged across a 25-minute decay.

**Net effect: the overlap gets worse, not better — 12.5% → 17.2%.** Both classes become
more distinctive individually, but the earthquake distribution widens enough that more of
it crosses the cascade's line. exp003's figure was optimistic by about five percentage
points.

## Which number should be quoted

**17.2%, the segment measurement.** Two reasons, and the second is the important one:

1. It is like-for-like — both classes measured over the same span from their own onset,
   rather than one class being averaged over a window it fills and the other over a
   window it does not.
2. **It is what an operational detector can actually compute.** GHADI's whole purpose is
   to decide within 180 s of initiation. A feature requiring 35 minutes of post-onset
   data is unavailable at decision time by definition. The whole-window figures were
   never operationally realisable; they were a retrospective convenience.

That second point is a design consequence, not just a reporting one: **the M3 classifier
must be trained on features computed over a decision-time segment**, not over a window
that extends beyond the moment the alert has to fire. Training on whole-window features
and deploying on segments would be a train/serve skew with a safety cost.

## What this does not change

- exp003's ordering results stand: the cascade sits at the low-frequency edge of the
  earthquake distribution, and the magnitude confound is unaffected.
- The positive class is still n = 1. All of the above is one event against 64.
- 120 s is a choice, not a derived value. It was not tuned — it was picked once as a
  plausible decision-time budget inside the 180 s end-to-end target, and the experiment
  was run once. A sensitivity sweep over segment length belongs with issue 2.6, on a
  corpus large enough that the choice can be justified rather than asserted.
