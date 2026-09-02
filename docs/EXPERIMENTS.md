# Experiment index

Experiments are immutable once run. A new question gets a new numbered directory —
never an edit to an old one. Negative results are committed, not deleted.

| ID | Question | Status | Headline finding |
|---|---|---|---|
| [exp001_signal_recon](../experiments/exp001_signal_recon/FINDINGS.md) | Is the 26 Aug 2026 mass-movement signal present and separable on NK.KKN? | **Reproduced 2026-09-02** | Signal present and cleanly triggered. Both spectral orderings reproduce (cascade highest LF/HF, lowest centroid); absolute values differ ~3× from the original, traced to the unpublished low/high split frequency. The settling artefact is worse than documented — it survives the prescribed LTA-length guard when the taper is length-proportional. |
| [exp002_feature_rework](../experiments/exp002_feature_rework/FINDINGS.md) | Does the M2 feature rework survive contact with real data? | **Run 2026-09-02** | Mixed, and the negative half matters more. The signal-presence gate (2.3) works and fixes exp001's headline failure; response deconvolution (2.4) makes units physical without changing discrimination. **`emergence_s` still fails**: on a regional earthquake it measures the S−P interval rather than the source ramp, so it is contaminated by distance. Do not put it in the M3 classifier, and do not tune it on two events. |

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
| "First trigger in the window" is not a safe onset pick — a window cut on a catalogue time can contain an earlier unrelated event | to be honoured by issue 1.2 | exp002 |
