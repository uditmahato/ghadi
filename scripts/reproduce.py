"""Rebuild every experiment's results and check them against what is committed.

    python scripts/reproduce.py                 # offline, from the local cache
    python scripts/reproduce.py --online        # allow fetching what the cache lacks
    python scripts/reproduce.py --only exp017 exp027
    python scripts/reproduce.py --update        # keep the regenerated results

Each experiment's ``run.py`` is run in place. Its ``results.json`` is compared with the
committed one, number by number within a small tolerance, and then put back unless
``--update`` is given. The report says, for each experiment, one of:

* **reproduced**: the regenerated results match.
* **differs**: they do not, and the first differing paths are listed.
* **failed**: the script did not finish. Offline, that usually means the waveform or
  imagery cache does not hold what it needs; run once with ``--online``.
* **superseded**: the experiment's inputs or code were later revised on purpose, so it
  is not expected to regenerate. The reason and the experiment that replaced it are
  given.
* **no script**: the experiment has findings and results but no ``run.py`` (two early
  ones were produced by scripts under ``scripts/``).
* **live record**: part of the result is a record of a live run that cannot be
  regenerated; the regenerable part is checked.

The waveform and imagery caches are not in the repository. A fresh checkout reproduces
only the experiments that need no data until ``--online`` has filled the caches.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
EXPERIMENTS = REPO / "experiments"
# Keys whose values record when or where something ran, not what it found.
VOLATILE = {
    "generated_utc",
    "created_utc",
    "resolved_utc",
    "run_utc",
    "updated_utc",
    "probed_utc",
    "built_utc",
    "cache_hits",
}
# Experiments whose results hold a live record next to a regenerable part.
LIVE_RECORD = {"exp025_first_live_day": ("live_run",)}
# Values that hold the moment they were built and nothing the experiment measured.
BUILT_AT = {"exp011_lead_time_headline": ("sample_cap_budget_60s",)}
# Experiments not expected to regenerate, each with the reason. Their findings stand as
# a record of what was measured at the time; the later experiment named is the one to
# reproduce instead.
SUPERSEDED = {
    "exp001_signal_recon": "the feature set was reworked in exp002 and gained fields",
    "exp004_false_alarm_rate": "the noise corpus was corrected in exp009",
    "exp006_teleseism_suppression": "the noise corpus was corrected in exp009",
}
REL_TOL = 1e-6
ABS_TOL = 1e-9


def differences(a: Any, b: Any, path: str = "", out: list[str] | None = None) -> list[str]:
    """Paths where two JSON values differ, floats compared within a tolerance."""
    out = [] if out is None else out
    if len(out) >= 20:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key in VOLATILE:
                continue
            if key not in a or key not in b:
                out.append(f"{path}/{key}: only in {'committed' if key in a else 'regenerated'}")
            else:
                differences(a[key], b[key], f"{path}/{key}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b, strict=True)):
                differences(x, y, f"{path}[{i}]", out)
    elif isinstance(a, bool) or isinstance(b, bool):
        if a != b:
            out.append(f"{path}: {a} vs {b}")
    elif isinstance(a, int | float) and isinstance(b, int | float):
        fa, fb = float(a), float(b)
        both_nan = math.isnan(fa) and math.isnan(fb)
        if not both_nan and not math.isclose(fa, fb, rel_tol=REL_TOL, abs_tol=ABS_TOL):
            out.append(f"{path}: {a} vs {b}")
    elif a != b:
        out.append(f"{path}: {str(a)[:40]!r} vs {str(b)[:40]!r}")
    return out


def run_one(exp: Path, online: bool, update: bool, timeout_s: float) -> dict[str, Any]:
    name = exp.name
    script = exp / "run.py"
    results = exp / "results.json"
    if not script.exists():
        return {"experiment": name, "status": "no script"}
    if not results.exists():
        return {"experiment": name, "status": "no committed results"}
    committed = json.loads(results.read_text(encoding="utf-8"))
    env = dict(os.environ)
    if online:
        env.pop("GHADI_OFFLINE", None)
    else:
        env["GHADI_OFFLINE"] = "1"
    backup = Path(tempfile.mkdtemp()) / "results.json"
    shutil.copy2(results, backup)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        seconds = round(time.monotonic() - started, 1)
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
            return {"experiment": name, "status": "failed", "seconds": seconds, "detail": tail}
        regenerated = json.loads(results.read_text(encoding="utf-8"))
        skip = LIVE_RECORD.get(name, ()) + BUILT_AT.get(name, ())
        a = {k: v for k, v in committed.items() if k not in skip}
        b = {k: v for k, v in regenerated.items() if k not in skip}
        diffs = differences(a, b)
        status = "reproduced" if not diffs else "differs"
        rec: dict[str, Any] = {"experiment": name, "status": status, "seconds": seconds}
        if diffs and name in SUPERSEDED:
            rec["status"] = "superseded"
            rec["reason"] = SUPERSEDED[name]
        if skip:
            rec["live_record"] = list(skip)
        if diffs:
            rec["differences"] = diffs
        return rec
    except subprocess.TimeoutExpired:
        return {"experiment": name, "status": "failed", "detail": [f"timed out after {timeout_s}s"]}
    finally:
        if not update:
            shutil.copy2(backup, results)
        shutil.rmtree(backup.parent, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--online", action="store_true", help="allow network fetches")
    parser.add_argument("--update", action="store_true", help="keep regenerated results")
    parser.add_argument("--only", nargs="*", default=None, help="experiment name prefixes")
    parser.add_argument("--timeout", type=float, default=3600.0, help="seconds per experiment")
    parser.add_argument("--report", type=Path, default=None, help="write the report as JSON")
    args = parser.parse_args(argv)

    experiments = sorted(
        p for p in EXPERIMENTS.iterdir() if p.is_dir() and p.name.startswith("exp")
    )
    if args.only:
        experiments = [p for p in experiments if any(p.name.startswith(x) for x in args.only)]
    report = []
    for exp in experiments:
        print(f"{exp.name} ...", flush=True)
        rec = run_one(exp, args.online, args.update, args.timeout)
        report.append(rec)
        line = f"   {rec['status']}"
        if "seconds" in rec:
            line += f" in {rec['seconds']} s"
        print(line, flush=True)
        if "reason" in rec:
            print(f"      {rec['reason']}")
            continue
        for d in rec.get("differences", [])[:5]:
            print(f"      {d}")
        for d in rec.get("detail", []):
            print(f"      {d[:160]}")
    counts: dict[str, int] = {}
    for rec in report:
        counts[rec["status"]] = counts.get(rec["status"], 0) + 1
    print("\n" + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    if args.report:
        args.report.write_text(json.dumps({"counts": counts, "experiments": report}, indent=2))
    fine = ("reproduced", "no script", "superseded")
    return 0 if all(r["status"] in fine for r in report) else 1


if __name__ == "__main__":
    sys.exit(main())
