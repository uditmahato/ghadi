# Experiment 001 — Signal reconnaissance on NK.KKN

**Question.** Is the 26 August 2026 mass-movement signal present on Nepal's one open
broadband station, and does it separate from real earthquakes and from quiet noise?

**Status: awaiting reproduction in this repository.** The findings below are the
original run of 2026-09-02 as recorded in [HANDOFF §2.2](../../docs/HANDOFF.md). The
harness here (`run.py`) is a fresh implementation; its numbers have not yet been
compared against the table below. **When it is first run, record the reproduced values
alongside the originals and document any divergence rather than overwriting.**

## Design

Four windows on `NK.KKN..BHZ` (50 Hz), analysis band 0.5–20 Hz: the cascade, two real
regional earthquakes from the USGS catalogue on the same station, and a quiet-noise
window at the same clock time one week earlier — the last controls for diurnal
cultural noise, which would otherwise be a plausible alternative explanation for any
separation found.

## Original results (2026-09-02)

| Case | Class | Emergence (s) | LF/HF ratio | Kurtosis | Spectral centroid (Hz) | Max STA/LTA |
|---|---|---:|---:|---:|---:|---:|
| 26 Aug 2026 Bhote Koshi | mass movement | 46.6 | **13.65** | 90.6 | **1.44** | 16.68 |
| Reference EQ, 18 Aug 2026 | earthquake | 307.1 | 0.87 | 152.4 | 3.85 | 25.76 |
| Reference EQ, 19 Jul 2026 | earthquake | 31.0 | 4.74 | 210.9 | 3.19 | 27.29 |
| Quiet noise, 19 Aug 2026 | noise | 254.6 | 3.75 | 3.20 | 2.76 | 6.69 |

## Findings

**1 — The signal is unambiguous.** SNR 85.2 dB, peak STA/LTA 16.7, a 67-second trigger
window. The spectrogram shows a sharp onset followed by a low-frequency-dominated tail
persisting for more than 25 minutes.

**2 — The spectral discriminants separate cleanly, exactly as the physics predicts.**
LF/HF is 13.65 for the cascade against 0.87 and 4.74 for two real earthquakes and 3.75
for noise; spectral centroid is 1.44 Hz against 2.76–3.85 Hz for everything else. A
spatially extended, slow, low-stress-drop source radiates low-frequency energy; a sharp
tectonic rupture does not. That is the separation GHADI is built on, and it is present
in real data on the first look.

**3 — The timing is tighter than any published account.** Main trigger onset at
**02:52:24 UTC**. Correcting for ~15 s of travel time over 55.9 km puts source
initiation at approximately **02:52:10 UTC = 08:37:10 NPT**, against published reports
giving only "~08:37–08:40". This is the anchor for every lead-time calculation the
project will make, and it is why the catalogue entry carries
`origin_uncertainty_s: 15` with `time_source: seismic`.

**4 — A genuine negative result, and the most useful thing in the experiment.** The
hand-specified composite score ranked **noise highest (0.823), above the actual target
(0.726)**. Two defects cause this:

- `emergence_s` is measured from 10% to 90% of the *global window peak*. When the peak
  is not the event, or the window is noise with no true peak, the feature is
  meaningless — hence 307 s for an earthquake and 254 s for noise. It must be
  redefined relative to the trigger onset (issue 2.1).
- `duration_ratio` rewards energy spread evenly across the window, which is the
  definition of noise. It needs a signal-presence gate (issue 2.3).

**Consequences carried into this repository:** the composite score does not exist in
`ghadi.features` (issue 3.6, guarded by `tests/test_features.py`), and the broken
emergence feature is named `emergence_s_global_peak` and marked DEPRECATED so it
cannot be mistaken for the fixed version.

**5 — A known artefact developers will hit immediately.** Every case produced a
spurious trigger at exactly **+60 s**, because the 60-second LTA had not settled. The
first LTA-length of every window must be discarded. Implemented in
`ghadi.detect.sta_lta` (the settling region is NaN, not a number) and asserted by
`tests/test_sta_lta.py::test_no_trigger_survives_at_the_lta_settling_boundary`. Never
let such a trigger into a training set as a positive.

## What this experiment does not show

- Nothing about **real-time** performance: these are archive retrievals. Latency is
  unmeasured (issue 0.1) and is the project's go/no-go.
- Nothing about **false-alarm rate**: four windows is not a corpus. FAR per
  station-month requires the ≥6 months of continuous noise gathered in M1.
- Nothing about **smaller events**: the 2026 cascade is the largest case available. A
  detector tuned on it may not generalise down, which is precisely why M2 must fix the
  temporal features rather than leaning on two correlated spectral ones.
