# GHADI

**Sub-hourly detection of cascading flood surges in transboundary Himalayan rivers.**

*(घडी — "clock/watch"; the point of the system is time.)*

## The one-line scope

**Detection, not prediction.** GHADI does not forecast when a slope will fail. It hears
the slope fail — from continuous seismic waveforms on open FDSN data — corroborates the
detection against an independent downstream river-gauge rate-of-rise anomaly, and emits
a CAP 1.2 alert into the SMS and siren infrastructure Nepal already operates.

On 26 August 2026, an ice-rock mass detached inside Tibet, dammed the Lhende Khola, and
the dam-break surge raised the Trishuli ~9 m in 30 minutes. It was not raining, so every
rainfall-driven system was blind. The initiating mass movement produced a seismic signal
strong enough that USGS initially catalogued it as an M4.4 earthquake. That signal was
public, minutes before the water. Nobody was listening. GHADI listens.

## Non-goals — write these on the wall

- Earthquake prediction (not scientifically possible)
- Another rainfall-driven flood forecast model
- A general "disaster AI platform" (Nepal has BIPAD; we emit into it)
- Public auto-alerting in v1
- Anything requiring new field hardware in phase 1

See [docs/HANDOFF.md](docs/HANDOFF.md) for the full engineering plan and
[docs/RESEARCH_REPORT.md](docs/RESEARCH_REPORT.md) for the evidence base.

## Quickstart

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                      # create .venv and install all dependencies
uv run pytest                # run the test suite (network-free)
uv run ruff check .          # lint
uv run mypy src              # type-check
```

Reproduce Experiment 001 (fetches ~4 waveform windows from EarthScope on first run,
then works from the local cache):

```bash
uv run python experiments/exp001_signal_recon/run.py
```

Measure real-time SeedLink latency for NK.KKN (issue 0.1 — the project's go/no-go):

```bash
uv run python scripts/seedlink_latency.py --hours 168 --out latency_log.csv
uv run python scripts/seedlink_latency.py --report latency_log.csv
```

## Repository conventions

- `main` is always green. Branch per issue, named like `m2/emergence-rework`.
- Commits explain *why*, not what.
- Experiments are immutable once run — a new question gets a new experiment directory.
- Negative results are committed, never deleted.
- Every timestamp is timezone-aware UTC. Nepal Standard Time is **UTC+05:45**.
- No generative model ever produces a number. Templates only.
- `status` must never be `Actual` and `scope` must never be `Public` in any
  non-authorised build. There is a test for this. Do not skip it.

## Layout

```
src/ghadi/          the package: config, catalog, fdsn, features, detect/, hydro,
                    fusion, cap, travel (M4), service (M5)
data/catalog/       committed event definitions (YAML, schema-validated)
data/cache/         gitignored content-addressed MiniSEED cache
experiments/        immutable experiment directories with FINDINGS.md
scripts/            operational scripts (SeedLink latency probe, bulk fetch)
tests/              network-free test suite; run with GHADI_OFFLINE=1 in CI
docs/               handoff, research report, architecture, data sources, ADRs
```
