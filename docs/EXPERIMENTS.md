# Experiment index

Experiments are immutable once run. A new question gets a new numbered directory —
never an edit to an old one. Negative results are committed, not deleted.

| ID | Question | Status | Headline finding |
|---|---|---|---|
| [exp001_signal_recon](../experiments/exp001_signal_recon/FINDINGS.md) | Is the 26 Aug 2026 mass-movement signal present and separable on NK.KKN? | **Reproduced 2026-09-02** | Signal present and cleanly triggered. Both spectral orderings reproduce (cascade highest LF/HF, lowest centroid); absolute values differ ~3× from the original, traced to the unpublished low/high split frequency. The settling artefact is worse than documented — it survives the prescribed LTA-length guard when the taper is length-proportional. |
| [exp002_feature_rework](../experiments/exp002_feature_rework/FINDINGS.md) | Does the M2 feature rework survive contact with real data? | **Run 2026-09-02** | Mixed, and the negative half matters more. The signal-presence gate (2.3) works and fixes exp001's headline failure; response deconvolution (2.4) makes units physical without changing discrimination. **`emergence_s` still fails**: on a regional earthquake it measures the S−P interval rather than the source ramp, so it is contaminated by distance. Do not put it in the M3 classifier, and do not tune it on two events. |
| [exp003_corpus_separation](../experiments/exp003_corpus_separation/FINDINGS.md) | Does the spectral separation survive a real earthquake corpus (n=64)? | **Run 2026-09-02** (carries an appended correction) | **The clean-separation claim is retired.** 12.5% of real earthquakes look at least as mass-movement-like as the cascade on both features at once; against magnitude- and distance-matched events that falls to 1 in 25. Magnitude, not distance, is the confound (rank r ±0.4). A third of corpus windows contained a pre-origin trigger. **Its availability claim was over-read and is withdrawn — see the correction at the top.** |
| [exp004_false_alarm_rate](../experiments/exp004_false_alarm_rate/FINDINGS.md) | What false-alarm rate does the detector run at against 226 h of noise? | **Run 2026-09-02** | **12.9 per station-month against a target of ≤1.** The spectral criteria do most of the work (30× reduction from the STA/LTA baseline's 387), and the signal-presence gate removes nothing. **Two of the four false alarms are confirmed teleseisms** — distant earthquakes look low-frequency because attenuation strips the highs, so they are not separable on these features and must be suppressed by global-catalogue cross-check instead. POD is not estimable at n=1: this is half an ROC. |
| [exp006_teleseism_suppression](../experiments/exp006_teleseism_suppression/FINDINGS.md) | How much does suppressing distant earthquakes buy? | **Run 2026-09-02** | **False-alarm rate halves, 12.9 → 6.5 per station-month.** Getting there required fixing the rule: a tolerance around **P** caught only one of two, because STA/LTA fires on the largest arrival, which for a distant event is S/Lg or the surface train — one trigger landed 647 s after P and 24 s after Lg. Suppression is a **P-to-surface phase window**, not a tolerance. Over-suppression is 8.3% of triggering windows, and the cascade itself survives (asserted in tests). |
| [exp005_window_length](../experiments/exp005_window_length/FINDINGS.md) | Is the separation an artefact of measuring over a 35-minute window? | **Run 2026-09-02** | No, but exp003 was mildly optimistic. Background is high-frequency (centroid 5.03 Hz) and does dilute short events, yet energy dominates duration so the effect is small. Measured like-for-like on 120 s segments the overlap is **17.2%, not 12.5%** — and the segment figure is the only operationally realisable one, since a 35-minute feature is unavailable at decision time. |

## Standing consequences for the codebase

Things later work must not undo, each traceable to an experiment:

| Consequence | Where enforced | From |
|---|---|---|
| No hand-weighted composite score | `tests/test_features.py` | exp001 Finding 4 |
| `emergence_s` measured against the global peak is deprecated, not the M2 fix | `ghadi.features` | exp001 Finding 4 |
| Settling guard covers **taper + LTA**, not LTA alone | `ghadi.detect.sta_lta` | exp001 Finding 5 |
| The preprocessing taper is a fixed duration, never a fraction of the window | `ghadi.features.preprocess`, `tests/test_sta_lta.py` | exp001 Finding 5 |
| An LF/HF ratio is meaningless without its split frequency | to be honoured by issue 2.6 | exp001 Finding 2 |
| Onset time is threshold-dependent for an emergent source; publish the threshold with any lead-time figure | to be honoured by M5 | exp001 Finding 3 |
| Emergence needs a signal-presence gate as well as an onset — 2.1 and 2.3 are one issue | `ghadi.features`, `tests/test_features.py` | exp002 |
| The emergence search is bounded, which keeps it causal and stops it spanning two arrivals | `ghadi.features`, `tests/test_features.py` | exp002 |
| `emergence_s` is excluded from the M3 classifier until distance contamination is resolved | to be honoured by M3 | exp002 |
| "First trigger in the window" is not a safe onset pick — a window cut on a catalogue time can contain an earlier unrelated event | `ghadi.detect.onset`, `scripts/harvest_earthquakes.py` | exp002, confirmed at scale by exp003 (a third of windows) |
| Never describe the spectral separation as "clean" — 12.5% of real earthquakes meet the cascade's own values on both features | to be honoured by every paper and README | exp003 |
| A classifier over these features must control for magnitude, or it learns a size detector rather than a mass-movement detector | to be honoured by M3 | exp003 |
| Report the assumed operating point's margin: a threshold at the cascade's own value is fitted to one event and is a lower bound, not an estimate | to be honoured by issue 3.5 | exp003 |
| Train and evaluate on features computed over a **decision-time segment**, never a window extending past the moment the alert must fire — otherwise train/serve skew with a safety cost | to be honoured by M3 | exp005 |
| Quote 17.2% as the earthquake overlap, not 12.5% | to be honoured by every paper and README | exp005 |
| Teleseism suppression by global-catalogue cross-check is an architectural component, not a later filter — distant earthquakes are not separable from mass movements on the spectral features | `ghadi.teleseism` | exp004, implemented after exp006 |
| Suppression spans a **P-to-surface phase window**, never a tolerance around P — STA/LTA fires on the largest arrival, which for a distant event is S/Lg or the surface train | `ghadi.teleseism`, `tests/test_teleseism.py` | exp006 |
| Any suppressor must be asserted not to remove the 26 Aug 2026 cascade — the worst and quietest failure is one that improves every false-alarm metric by eating the target | `tests/test_teleseism.py` | exp006 |
| Extend the noise-corpus exclusion catalogue to global M≥5.5 with travel-time-aware windows, not M≥3.5 within 6° | to be honoured by issue 1.3 | exp004 |
| Never quote a false-alarm rate as detector performance while POD is unestimable at n=1 | to be honoured by every paper | exp004 |
