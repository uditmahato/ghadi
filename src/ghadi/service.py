"""Real-time loop, health monitoring, and the append-only audit log — M5, not started.

Blocked on M0 issue 0.1: until real-time NK.KKN latency over SeedLink is measured,
there is no basis for designing this loop. If latency exceeds ~120 s the project
becomes retrospective-analysis-only and must be re-scoped honestly (Blocker B4).

When built, the audit log is append-only and tamper-evident, recording per decision:
input snapshot hash, model version, score, gate decision, operator identity, and
dissemination result. That log is what makes accountability possible after a false
alarm or a missed event, and — given the DRRM Regulations' language about not causing
"unnecessary panic" — it is the artefact that protects the operator.

Use ``scripts/seedlink_latency.py`` to run the measurement that unblocks this module.
"""

from __future__ import annotations


def run_forever() -> None:
    """Run the real-time detection loop.

    Raises:
        NotImplementedError: always, until M5.
    """
    raise NotImplementedError(
        "The real-time service is M5 and is blocked on the SeedLink latency "
        "measurement (issue 0.1). Run scripts/seedlink_latency.py first."
    )
