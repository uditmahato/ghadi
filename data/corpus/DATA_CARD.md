# Data card — GHADI seismic corpora (issue 1.6)

Provenance, composition and known gaps for the labelled corpora under `data/corpus/`.
Manifests are committed; the waveforms they reference live in the gitignored
content-addressed cache and are re-fetchable from EarthScope by re-running the harvest.

## Corpora

| File | Label | Status |
|---|---|---|
| `earthquakes.json` | earthquake | 150 candidates, **64 usable** (harvested 2026-09-02) |
| `noise.json` | noise | **366 usable** windows (213.5 h). Re-harvested 2026-09-03 with global teleseism exclusion — 27 windows previously labelled noise held real distant earthquakes (exp009) |
| `availability.json` | — | monthly archive-coverage probe, 2016-05 to 2026-08 |
| `exclusion_catalogue.json` | — | regional earthquakes excluded from the noise corpus |
| `global_catalogue.json` | — | 1,133 global M≥5.5 origins, for teleseism exclusion and runtime suppression |
| `earthquakes_IO_EVN.json` | earthquake | **132 usable** (harvested 2026-09-06). Second station, deeper near-field coverage (60 within 100 km); features NOT interchangeable with NK.KKN's — per-station only (exp007) |
| positives | mass_movement | **n = 1 usable.** See "The class imbalance that matters" |

## Archive coverage constrains everything below

`NK.KKN..BHZ` advertises continuous operation from 2016-05-22, open-ended. The archive
holds data at the probe point in **71 of 124 months**: nothing before ~2020-03, and gaps
at 2025-01 and 2025-08 through 2025-12. **Usable history is roughly 3.8 years shorter
than the station metadata implies**, and any corpus drawn without checking
`availability.json` will silently sample dead months — the first noise-corpus attempt
returned 2 usable windows from 80 for exactly that reason. Full map in
[docs/DATA_SOURCES.md](../../docs/DATA_SOURCES.md).

## earthquakes.json

**Provenance.** USGS FDSN event service, M ≥ 4.0 within 4° of 28.255 °N 85.520 °E
(the 2026 source zone), 2016-05-22 (NK.KKN start) to 2026-08-25 (before the cascade, so
the target event cannot leak into the negative class). Waveforms `NK.KKN..BHZ` from
EarthScope, 2100 s per window (600 s before origin, 1500 s after).

**Composition of the 64 usable events.**

| Distance | n | | Magnitude | n |
|---|---:|---|---|---:|
| 0–100 km | 1 | | M4.0–4.5 | 40 |
| 100–200 km | 8 | | M4.5–5.0 | 18 |
| 200–300 km | 41 | | M5.0–5.5 | 4 |
| 300–400 km | 7 | | M5.5–6.0 | 2 |
| 400+ km | 7 | | M6.0+ | 0 |

**Known gaps and biases — read these before using it.**

1. **Near-field coverage is nearly absent.** Only 1 event within 100 km and 9 within
   200 km, while the target cascade was at 55.9 km. Any comparison against the corpus
   as a whole is a comparison against *distant* earthquakes. exp003 found distance does
   not correlate with the spectral features here (rank r ≈ +0.04), but that null result
   rests on this thin near-field sample and should not be trusted far.
2. **86 candidates have no archived waveform, clustered on 2025-01-07** (the M7.1 Tibet
   sequence). Missingness is not random and correlates with the largest events in the
   query window, so the corpus under-represents exactly the strongest regional shaking.
   See [DATA_SOURCES.md](../../docs/DATA_SOURCES.md).
3. **No M ≥ 6.0 events at all.** The corpus cannot say how the features behave for the
   largest earthquakes, which are the ones most likely to be confused with a large mass
   movement on a low-frequency criterion.
4. **Magnitude is a confound, and it is in the data.** Rank correlation +0.44 between
   LF/HF and magnitude, −0.42 for the centroid. A model trained without controlling for
   size may learn a size detector (exp003).
5. **Onsets are picked by causality, not by first trigger.** 32 pre-origin triggers were
   rejected across 21 of the 64 windows. Under a first-trigger rule a third of this
   corpus would carry features computed from an unrelated transient
   (`ghadi.detect.onset`).
6. **One station, one channel.** BHZ vertical only. No three-component features yet
   (issue 2.5).
7. **Catalogue magnitudes are heterogeneous** — `magnitude_type` varies across entries
   and is recorded per event but not harmonised.

**Failure rows are retained.** Every candidate stays in the manifest with a `status`
and a `reason`. A corpus that silently drops what it could not process misreports its
own completeness.

## The class imbalance that matters

The corpus has 64 negatives and **one** positive — the 26 August 2026 cascade. Of the
six seed catalogue events, Jure 2014 and Langtang 2015 predate the station, and Thame
2024, Melamchi 2021 and Rasuwagadhi 2025 have origin times derived from news reports
with uncertainties of 1–3 hours, which is too coarse to cut a labelled window around
without further work.

**Five more positives are reachable on IO.EVN** (exp007), which holds all six
candidate events including Gorkha 2015 and Jure 2014 that NK.KKN cannot reach. That
makes R1 less severe than it looks here, but nothing has yet turned availability into a
labelled window: four of the six still carry news-derived origin times with one-to-three
hour uncertainties, and "has data" is not "has a detectable signal".

**No amount of earthquake harvesting on a single station fixes this.** It is risk R1 in its most concrete
form, and it is why the handoff proposes the Gorkha co-seismic landslide population
(issue 1.5) — signals buried in the mainshock coda, which is a research problem in its
own right — and why the honest deliverable may be a well-characterised physics detector
rather than a learned one.

## Splits

Use `ghadi.splits`. Event holdout, temporal holdout and leave-one-event-out are
implemented and random windowed splitting is refused in code (issue 1.4). With one
positive event, leave-one-event-out on the positive class is degenerate: **report
per-event results, never pooled**, and say plainly that the positive class is n = 1.

## Licence and reuse

Waveforms are open FDSN data from EarthScope; the USGS event catalogue is public
domain. The manifests and derived features in this repository carry the repository's
MIT licence. No personal data of any kind is present, and none is needed.
