# Experiment 001 — Signal reconnaissance on NK.KKN

> **Superseded in part by [exp003](../exp003_corpus_separation/FINDINGS.md).** Finding 2
> below describes the spectral separation as "clean". That was measured against two
> earthquakes. Against a corpus of 64, 12.5% of real earthquakes meet the cascade's own
> values on both spectral features simultaneously. The separation is a tendency, not a
> boundary. This document is left unedited because experiments are immutable; read
> exp003 before quoting anything here about separability.

**Question.** Is the 26 August 2026 mass-movement signal present on Nepal's one open
broadband station, and does it separate from real earthquakes and from quiet noise?

**Status: reproduced in this repository on 2026-09-02.** The original run is recorded
in [HANDOFF §2.2](../../docs/HANDOFF.md); the harness here (`run.py`) is an independent
re-implementation. Both sets of numbers are given below. **Where they diverge, the
divergence is documented rather than reconciled away.**

## Design

Four windows on `NK.KKN..BHZ` (50 Hz), analysis band 0.5–20 Hz, 35 minutes each: the
cascade, two real regional earthquakes from the USGS catalogue on the same station, and
a quiet-noise window at the same clock time one week earlier — the last controls for
diurnal cultural noise, which would otherwise be a plausible alternative explanation
for any separation found.

Reference earthquakes are resolved once and cached in `reference_events.json`, so the
comparison cannot silently change under a catalogue revision or a service outage.

## Results

Original run (HANDOFF §2.2), then this reproduction:

| Case | Class | LF/HF (orig → repro) | Centroid Hz (orig → repro) | Max STA/LTA (orig → repro) |
|---|---|---|---|---|
| 26 Aug 2026 Bhote Koshi | mass movement | **13.65 → 4.14** | **1.44 → 2.04** | 16.68 → 9.50 |
| Reference EQ, 18 Aug 2026 (M4.3) | earthquake | 0.87 → 0.39 | 3.85 → 5.74 | 25.76 → 11.95 |
| Reference EQ, 19 Jul 2026 (M4.5) | earthquake | 4.74 → 0.76 | 3.19 → 3.93 | 27.29 → 11.99 |
| Quiet noise (T−7d) | noise | 3.75 → 0.69 | 2.76 → 5.40 | 6.69 → 1.86 |

Independently confirmed, exactly: the station metadata (27.800 °N, 85.279 °E, 2042 m,
BHZ/BHN/BHE at 50 Hz, operating 2016-05-22 open-ended), the **105,001 samples** returned
for the event window, and the identity of both reference earthquakes.

## Findings

**1 — The signal is present and unambiguous.** Reproduced. The cascade window yields a
single clean trigger with peak STA/LTA 9.50 lasting 47 s, against zero triggers in the
noise window. Envelope RMS over 30-second blocks rises from ~88 (pre-event) to 692,
5806 and 8353 across t = 600–690 s, which is the surge arriving.

**2 — The spectral discriminants separate cleanly, and the separation is if anything
cleaner than originally reported.** Reproduced in direction, not in magnitude. The
cascade has the highest low-to-high frequency ratio (4.14 against 0.39–0.76 for the two
earthquakes) and the lowest spectral centroid (2.04 Hz against 3.93–5.74 Hz). Both
orderings — the ones the project's thesis rests on — hold.

Notably the noise window behaves *better* here than in the original: it scored LF/HF
3.75 and centroid 2.76 Hz originally, which made it look cascade-like on both features
and is the direct cause of Finding 4's failure. In this reproduction noise scores 0.69
and 5.40 Hz, resembling an earthquake far more than a mass movement.

**A caveat that must be carried into M2.** The absolute ratios differ by roughly 3×
between the two implementations. The most likely cause is the low/high split frequency,
which this implementation sets at 3.0 Hz (`SeismicConfig.spectral_split_hz`) and which
the original run does not state. **An LF/HF ratio is not a portable number unless the
split frequency is published alongside it**, and the same applies to the PSD estimator's
parameters. Issue 2.6 (quantify separation per feature with bootstrap confidence
intervals) must report the split it used, or its numbers will not be comparable either.

**3 — Timing.** This run puts the trigger onset at **02:52:30.3 UTC**, against the
original's 02:52:24 — about 6 seconds later. Correcting for ~15 s of travel time over
55.9 km gives source initiation at ≈02:52:15 UTC = 08:37:15 NPT, against the original's
02:52:10 = 08:37:10.

The difference is trigger-threshold sensitivity on an emergent onset: this run uses
`trigger_on = 5.0`, and a lower threshold fires earlier on a signal that ramps rather
than jumps. **This is not a rounding disagreement, it is the central difficulty of the
whole project** — an emergent source has no sharp arrival to timestamp, so "onset" is
threshold-dependent by nature. Any published lead-time figure must state the threshold
that produced it, and M2's redefinition of `emergence_s` relative to trigger onset
inherits this sensitivity.

The catalogue entry retains `origin_uncertainty_s: 15`, which comfortably spans both
estimates. That is the value of carrying uncertainty rather than a point time.

**4 — The negative result reproduces.** The broken `emergence_s` measured against the
global window peak gives 28.3 s for the cascade but 287.9 s for one earthquake and
391.2 s for noise — the same pathology the original found (46.6 / 307.1 / 254.6). When
the window maximum is not the event, or the window is noise with no true peak, the
feature is meaningless. Issue 2.1 (redefine relative to trigger onset) stands.

Consequences already carried into the code: the composite score does not exist in
`ghadi.features` (issue 3.6, guarded by a test), and the broken feature is named
`emergence_s_global_peak` and marked deprecated so it cannot be mistaken for the fix.

**5 — The settling artefact reproduces, and is worse than documented.** The original
found a spurious trigger at exactly +60 s and prescribed discarding the first
LTA-length. **That is necessary but not sufficient.** This run initially produced a
spurious trigger at 61.3 s on the cascade window — 1.3 s *after* the prescribed guard
lifted — with the real event still 559 s away.

Cause: the preprocessing taper was a fraction of the window (`tukey(alpha=0.05)`),
which on a 35-minute window tapers **52.5 s at each end**. Those suppressed samples sit
inside the LTA's trailing window for a further `taper_s` after the taper itself ends, so
the LTA baseline is biased low and the ratio spikes to 5.4 the moment the STA clears the
taper, then collapses to 0.48. Measured directly: envelope RMS in the first 30 s block
was 10.0 after preprocessing against 398.5 in the raw trace.

Two fixes, both applied:

- the taper is now a fixed `taper_s = 5.0` seconds regardless of window length, since a
  taper exists to suppress filter edge transients and a few seconds does that at any
  length (`ghadi.features.preprocess`);
- the settling guard covers `taper_s + lta_s`, not `lta_s` alone
  (`ghadi.detect.sta_lta`).

After the fix the cascade window yields **one** trigger instead of two, at the real
event. `tests/test_sta_lta.py` asserts both that nothing fires inside the settling
region and that the tapered fraction shrinks as the window grows — the latter would have
caught this bug directly.

## What this experiment does not show

- Nothing about **real-time** performance: these are archive retrievals. Latency is
  unmeasured (issue 0.1) and remains the project's go/no-go.
- Nothing about **false-alarm rate**: four windows is not a corpus. FAR per
  station-month needs the ≥6 months of continuous noise gathered in M1.
- Nothing about **smaller events**: the 2026 cascade is the largest case available. A
  detector tuned on it may not generalise down — which is exactly why M2 must repair
  the temporal features rather than leaning on two correlated spectral ones.
- **Nothing about discrimination as such.** Four windows, one of each class, with
  features whose absolute values are implementation-sensitive, cannot establish
  separability. The orderings are encouraging and reproducible; they are not evidence
  of a usable detector.

## Reproducing

```bash
uv run python experiments/exp001_signal_recon/run.py
```

First run fetches from EarthScope into `data/cache`; afterwards it runs fully offline,
verified with `GHADI_OFFLINE=1`.
