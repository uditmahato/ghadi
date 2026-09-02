# GHADI Architecture

The authoritative diagram is §4 of [HANDOFF.md](HANDOFF.md). This document records the
rules that the code enforces and where each one lives.

## The two paths

```
DETECTION PATH (latency-critical, import-clean):
  fdsn/SeedLink -> features -> detect -> fusion -> cap
  DHM gauges    -> hydro    ----------^

ANALYSIS PATH (not latency-critical):
  satellite monitoring, event catalogue curation, retrospective replay,
  travel-time tables, exposure layers, figures
```

## The four architectural rules

| # | Rule | Enforced by |
|---|---|---|
| 1 | Detection path and analysis path are physically separate. The detection modules (`ghadi.features`, `ghadi.detect`, `ghadi.hydro`, `ghadi.fusion`, `ghadi.cap`) must not import anything that can block on a satellite API — concretely: no `obspy`, no `matplotlib`, no network clients. They operate on plain numpy arrays and dataclasses. | `tests/test_layering.py` (subprocess import check) |
| 2 | Degradation is a first-class output. Every fusion decision carries `channels_alive` / `channels_dead`, and alert text states them. | `ghadi.fusion.Decision`, `tests/test_fusion.py` |
| 3 | Corroboration requires source *independence*, not agreement count. Channels are collapsed into independence groups before noisy-OR. | `ghadi.fusion.fuse`, `tests/test_fusion.py` |
| 4 | No generative model ever produces a number. CAP text is built from strict templates over structured records. | `ghadi.cap` (template-only), code review |

## Latency budgets (handoff §5.1)

| Module | Budget |
|---|---|
| `features` | < 1 s per 240 s window, CPU |
| `detect.sta_lta` | < 100 ms |
| `detect.classify` | < 2 s (M3) |
| `hydro` | < 100 ms |
| `fusion` | < 50 ms |
| `cap` | < 50 ms |

End-to-end target: source initiation → CAP message ready ≤ 180 s.

## Hard interface rules (handoff §5.3)

- Every timestamp is timezone-aware UTC. NPT is UTC+05:45 (`ghadi.config.NPT`).
- Every catalogue entry carries `origin_uncertainty_s`; zero is forbidden for any event
  whose time is not instrumentally derived (`ghadi.catalog`).
- Every probability is calibrated and reported with an interval; no bare scalar without
  uncertainty in operational output.
- Every alert records the exact model version that produced it (`ghadi.cap`).

## Safety rules (handoff §15)

`status` never `Actual` and `scope` never `Public` unless the build is explicitly
authorised via the `GHADI_AUTHORIZED_BUILD=1` environment flag. Guard lives in
`ghadi.cap`; test in `tests/test_cap.py`. Do not skip it.
