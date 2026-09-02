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

## A measured availability gap on the primary station

Harvesting the reference-earthquake corpus (issue 1.2) returned **no archived waveform
for 86 of 150 catalogue events**, and the gap is not random:

| Date | Events with no waveform |
|---|---:|
| 2025-01-07 | **47** |
| 2025-01-08 | 8 |
| 2025-01-13 | 5 |
| everything else | 26 |

84 of the 86 fall in 2025. **2025-01-07 is the M7.1 Tibet earthquake**, and its entire
aftershock sequence is missing along with the mainshock. Whether this was a station
outage, a telemetry loss, or an archive gap cannot be determined from outside.

The operational implication is the same either way: **Nepal's one open broadband station
may be unavailable exactly when a large regional event occurs.** That is risk R4 with a
date attached. It is a specific question for the DMG/NEMRC letter (blocker B3), and it
strengthens the case for secondary stations (`IO.EVN`, `NQ.*`) being wired in earlier
than planned rather than treated as redundancy.

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
