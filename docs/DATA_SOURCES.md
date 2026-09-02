# Data sources, licences, and access status

Compiled from the research report §7 (full detail there). Status as of 2026-09-02.

## In use now

| Source | What | Access | Licence | Notes |
|---|---|---|---|---|
| EarthScope SeedLink (`rtserve.iris.washington.edu:18000`) | NK.KKN real-time stream | **PUBLIC, verified live 2026-09-02** | Open | p95 latency 22 s on a short sample — see [LATENCY.md](LATENCY.md) |
| EarthScope FDSN (`service.earthscope.org`) | NK network waveforms + station metadata | **PUBLIC, verified working** | Open FDSN terms | ObsPy client name `"EARTHSCOPE"` — `"IRIS"` is deprecated. **`SY.*` networks are synthetics and are excluded from every query** (enforced in `ghadi.fdsn`). |
| NK.KKN (Kakani broadband) | Primary station: 27.800°N 85.279°E, 2042 m, CMG-3T, BHZ/BHN/BHE @ 50 Hz, since 2016-05-22 | PUBLIC | Open | 55.9 km from the 2026 source zone. Events before 2016-05-22 (Jure 2014, Langtang 2015) have **no NK.KKN record** — expect fetch failures, by design. **See the availability gap below.** |
| USGS FDSN event service | Reference earthquake catalogue | PUBLIC | Open | 108 candidate events M≥4.3 within 4° of source, 2024-01-01→2026-08-25 (verified) |
| Secondary stations | `IO.EVN` (130.9 km), `NQ.KNSET`, `NQ.KTNP2` (strong-motion, Kathmandu), `K5.WANG` (Bhutan) | PUBLIC | Open | |

## Archive coverage on the primary station — measured, and not what the metadata says

The station metadata advertises `NK.KKN..BHZ` as operating continuously from
**2016-05-22, open-ended**. The archive does not hold that. A one-window-per-month probe
across the station's whole advertised life (`scripts/probe_availability.py`,
`data/corpus/availability.json`) found data at the probe point in **71 of 124 months**:

```
year  JFMAMJJASOND
2016  ........          <- nothing before 2020-03, despite metadata from 2016-05
2017  ............
2018  ............
2019  ............
2020  ..##########
2021  ############
2022  ############
2023  ######.#####
2024  ############
2025  .######.....      <- 2025-01 absent; 2025-08 to 2025-12 absent
2026  ########
```

**What the station claims to cover and what can actually be harvested are different
things**, and only the second matters for building a corpus. Consequences:

1. **Usable history starts around 2020-03, not 2016.** Roughly 3.8 years less than the
   handoff assumes. Any plan resting on ten years of archive should be re-scoped.
2. **2025-01 is a gap, which explains the 47 missing 2025-01-07 events** (the M7.1
   Tibet sequence). Earlier notes here read that as the station failing during a large
   event; the coverage map shows the gap was already there and the M7.1 fell inside it.
   That reading is **withdrawn** — see the correction at the top of
   [exp003 FINDINGS](../experiments/exp003_corpus_separation/FINDINGS.md).
3. **2025-08 to 2025-12 is a five-month gap**, which is why the first noise-corpus
   attempt returned 2 usable windows from 80 — it was sampling a period with no data.
4. A month marked present may still contain gaps. One probe per month cannot see them,
   and the corpus manifests record per-window failures for that reason.

This is a concrete question for the DMG/NEMRC letter (blocker B3): is the gap an
archiving policy, a telemetry loss, or data held locally at NEMRC but never forwarded to
EarthScope? The third case would be recoverable and would roughly double the usable
history. It also strengthens the case for wiring in secondary stations (`IO.EVN`,
`NQ.*`) earlier than planned.

## Blocked / negotiation required (owners in handoff §11)

| Source | Blocker | Fallback |
|---|---|---|
| DHM gauge telemetry at native sampling | **B2** — data-sharing agreement | Ship seismic-only detector; `ghadi.hydro` takes plain `(times_s, stage_m)` so the loader swaps in later |
| BIPAD API | **B1** — existence unconfirmed | CAP file drop; treat BIPAD as write-only |
| Real-time SeedLink latency | **B4** — preliminary result is good (p95 22 s, see [LATENCY.md](LATENCY.md)); the 7-day distribution issue 0.1 asks for is still outstanding | `scripts/seedlink_latency.py`, run for 7 days |
| Upstream Tibetan hydromet | **B5** — no agreement exists | This is why GHADI exists: infer the upstream event without it |

## Legal / compliance open items

- Legal basis for automated alerting (**B6**): DRRM Regulations bar transmitting information
  that "may create unnecessary panic or fear". Resolve with NDRRMA at tier T1, not T3.
- Nepal data-protection framework status: confirm with counsel before any personal-data
  work is scoped (issue 0.4). **The seismic and hydrological work needs no personal data.**

## Caching policy

All waveform/metadata fetches go through `ghadi.fdsn`'s content-addressed cache under
`data/cache/` (gitignored), keyed by NSLC + window. A second run must be offline and
byte-identical. `GHADI_OFFLINE=1` forbids network access entirely (CI default).
