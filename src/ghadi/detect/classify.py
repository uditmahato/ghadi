"""The learned mass-movement classifier — M3, not started.

Deliberately unimplemented. The milestone order is not negotiable: the temporal
features are broken (HANDOFF §2.2, Finding 4) and a classifier trained on the two
correlated spectral features alone will overfit and will not generalise to a smaller
event. M2 (feature rework) lands first.

When this is built, the exit criteria are fixed in advance (HANDOFF §7, M3):

- it must **beat STA/LTA on the emergent class**, with ROC and reliability diagram;
- probabilities must be calibrated (isotonic or Platt), never raw scores;
- the operating point must be selected under a *published* cost ratio with a
  sensitivity analysis;
- if it does not beat the baseline, that null result is the deliverable and is
  published, not deleted.

Latency budget when it exists: < 2 s.
"""

from __future__ import annotations

from ..features import Features


def classify(features: Features) -> float:
    """Return a calibrated probability that the window contains a mass movement.

    Raises:
        NotImplementedError: always, until M3.
    """
    raise NotImplementedError(
        "The learned classifier is M3 and depends on the M2 feature rework. "
        "Use ghadi.detect.sta_lta for the baseline. Do not add a hand-weighted "
        "composite score here — Experiment 001 showed one ranked noise above the "
        "actual target (issue 3.6)."
    )
