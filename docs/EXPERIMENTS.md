# Experiment index

Experiments are immutable once run. A new question gets a new numbered directory —
never an edit to an old one. Negative results are committed, not deleted.

| ID | Question | Status | Headline finding |
|---|---|---|---|
| [exp001_signal_recon](../experiments/exp001_signal_recon/FINDINGS.md) | Is the 26 Aug 2026 mass-movement signal present and separable on NK.KKN? | **Reproduced 2026-09-02** | Signal present and cleanly triggered. Both spectral orderings reproduce (cascade highest LF/HF, lowest centroid); absolute values differ ~3× from the original, traced to the unpublished low/high split frequency. The settling artefact is worse than documented — it survives the prescribed LTA-length guard when the taper is length-proportional. |

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
