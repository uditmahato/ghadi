"""Experiment 025: the first live day, replayed under today's code.

The live half of ``results.json`` is the shadow service's own audit log from
2026-09-26 08:29 to 2026-09-27 04:36 UTC and cannot be regenerated: it is what the
service recorded at the time, kept as recorded. This script regenerates the other half,
by replaying the same period from the archive through ``scripts/run_shadow.py`` with
the default settings (horizontals, IO.EVN as partner, the catalogue for the period).

    python experiments/exp025_first_live_day/run.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
START = "2026-09-26T08:20:00Z"
MINUTES = 1216


def decisions(audit: Path) -> list[dict[str, Any]]:
    out = []
    for line in audit.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        q = json.loads(line)["payload"]
        s, d = q["seismic"], q["decision"]
        hv = s.get("segment_hv")
        out.append(
            {
                "detected_utc": q["detected_utc"],
                "tier": d["tier"],
                "probability": d["probability"],
                "segment_lf_hf": round(s["segment_lf_hf"], 3),
                "segment_centroid_hz": round(s["segment_centroid_hz"], 3),
                "segment_hv": None if hv is None else round(hv, 3),
                "corroborated": s.get("corroborated"),
                "mass_movement_like": s["mass_movement_like"],
                "suppressed": s["suppressed"],
                "suppression_reason": s.get("suppression_reason") if s["suppressed"] else None,
            }
        )
    return out


def main() -> int:
    results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "run_shadow.py"),
                "replay",
                "--start",
                START,
                "--minutes",
                str(MINUTES),
                "--state-dir",
                tmp,
                "--quiet",
            ],
            check=True,
            cwd=REPO_ROOT,
        )
        state = Path(tmp) / "replay"
        status = json.loads((state / "status.json").read_text(encoding="utf-8"))
        results["replay_under_current_code"]["feed"] = status["feed"]
        results["replay_under_current_code"]["decisions"] = decisions(state / "audit.jsonl")
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    replay = results["replay_under_current_code"]["decisions"]
    print(f"live decisions: {len(results['live_run']['decisions'])}")
    print(f"replay decisions: {len(replay)}")
    print(f"mass movement like on replay: {sum(r['mass_movement_like'] for r in replay)}")
    print(f"set aside on replay: {sum(r['suppressed'] for r in replay)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
