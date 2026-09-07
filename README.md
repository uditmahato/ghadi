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

## What is actually established, as of 2026-09-02

Read this before quoting anything about GHADI's feasibility. Details and caveats in
[docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

**Encouraging.**

- The 26 August 2026 signal is present and cleanly triggered on NK.KKN, and the
  station's metadata and sample count reproduce the handoff's verified figures exactly.
- Real-time SeedLink latency is **median 15.8 s, p95 22.8 s, worst case 27.1 s** over
  3.4 continuous hours with **no interruption over 120 s** — well inside the viability
  threshold ([docs/LATENCY.md](docs/LATENCY.md)). The seven-day run issue 0.1 asks for
  is still outstanding; 3.4 hours cannot see diurnal structure or a monsoon outage.
- Against earthquakes matched for magnitude and distance, the cascade is distinctive:
  1 in 25 looks like it on both spectral features.
- **The separation is source physics, not a site effect.** It reproduces on a second
  independent station 131 km away (IO.EVN), where the cascade sits even further into
  the low-frequency tail — overlap 4.5% vs NK.KKN's 17.2% (exp010). This answered the
  most serious internal challenge to the project's premise.

**Sobering, and load-bearing.**

- **The spectral separation is not clean.** Against 64 real earthquakes, **17.2%** meet
  the cascade's own values on both features simultaneously, measured over the 120 s
  decision-time segment an operational detector could actually use. The earlier "clean
  separation" claim came from a comparison against two events (exp003, exp005).
- **The positive class is n = 1.** One usable mass-movement window exists. Two seed
  events predate the station; three have news-derived origin times too coarse to cut a
  window around ([data/corpus/DATA_CARD.md](data/corpus/DATA_CARD.md)).
- **The two spectral features encode one physical idea**, so they are correlated and
  fail together. Three-component polarisation is implemented but unmeasured.
- **The false-alarm rate is ~7× over target.** 6.8 per station-month against a target of
  ≤1, over 214 hours of correctly-labelled noise — with a 95% interval of roughly
  0.8–25, because it rests on two surviving events (exp004, exp006, exp009).
- **Distant earthquakes are not separable from mass movements on these features.** Half
  the false alarms were teleseisms: attenuation strips their high frequencies, so they
  arrive looking exactly like a slow extended source. `ghadi.teleseism` suppresses them
  by global-catalogue cross-check, which halved the rate — but only once the rule spanned
  a P-to-surface phase window rather than a tolerance around P (exp006).
- **Magnitude is a confound** (rank correlation ±0.4). A classifier that does not
  control for size may learn a size detector.
- **The archive is discontinuous, and shorter than the metadata claims.** NK.KKN
  advertises operation from 2016-05-22 but holds data at the probe point in only 71 of
  124 months, with nothing before ~2020-03 and a five-month gap in late 2025. Usable
  history is ~3.8 years shorter than the handoff assumes
  ([docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)).

Nothing here falsifies the core hypothesis. It does mean the question "can mass
movements be separated at a usable false-alarm rate" is still open, and is M3's to
answer on the corpus rather than on four windows.

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
