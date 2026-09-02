# ADR-0001: Repository tooling

**Status:** accepted · **Date:** 2026-09-02

## Context

The handoff (§13) sets the quality bar — type hints on public functions, unit tests for
every feature and threshold, a network-free test mode, CI green before merge — but does
not prescribe tooling. Development happens on Windows; the eventual deployment target
(DHM) is Linux.

## Decision

- **Python ≥ 3.12**, developed on 3.13, CI on 3.12. The floor is set by numpy's
  bundled type stubs, which use `type` statement syntax that mypy will not parse
  under 3.11 — claiming 3.11 support we cannot type-check would be a lie in the
  metadata.
- **uv** for environments and locking (`uv.lock` committed). Fast, reproducible,
  works identically on Windows and Linux.
- **ruff** for lint + format (one tool instead of black/flake8/isort).
- **mypy** with `disallow_untyped_defs` on `src/ghadi`.
- **pytest** with `GHADI_OFFLINE=1` in CI so no test can silently depend on the network.
- **CI on both `ubuntu-latest` and `windows-latest`** to catch path/encoding drift
  between the dev machine and the deployment target early.
- **Detection-path purity enforced by test, not convention**: `tests/test_layering.py`
  imports the detection modules in a clean subprocess and fails if `obspy`,
  `matplotlib`, or any network client got imported (Architectural rule 1).

## Consequences

- Contributors need uv (`pip install uv` suffices).
- ObsPy lives only in the fetch layer (`ghadi.fdsn`) and scripts/experiments; detection
  modules operate on numpy arrays, which keeps the latency-critical path lean and makes
  the layering testable.
- MIT licence; whether the repo goes public is the lead's call (handoff §16 Q4) and is
  not blocked by anything here.
