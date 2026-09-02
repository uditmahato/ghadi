# GHADI — Developer Handoff and Engineering Plan

**Project:** Sub-hourly detection of cascading flood surges in transboundary Himalayan rivers
**Version:** 1.0 · 2 September 2026
**Audience:** the engineering lead who will plan and staff this, and the developers who will build it
**Companion document:** *AI for Natural-Disaster Risk Reduction in Nepal* (the research report). This handoff assumes it but does not require it — everything needed to plan is restated here.

---

## 0. How to read this document

This is a planning document, not a specification to implement line by line. It is organised so that a lead can:

1. decide in ten minutes whether the project is real (§1–§3),
2. staff and schedule it (§7–§10),
3. hand individual issues to developers (§8),
4. and know exactly what will kill it (§11).

Claims are tagged the same way as the research report: **[E]** evidence with a source, **[I]** inference, **[H]** hypothesis to be tested. **[V]** marks something *verified during the preparation of this handoff* — a fact established by running code against live data on 2 September 2026, not taken from a paper.

---

## 1. What you are building, in one page

### The problem

On **26 August 2026**, an ice-and-rock mass detached from a slope near Langtang Lirung **inside Tibet**, fell roughly 1,200 m into the Lhende Khola, formed a temporary debris dam, and failed within about three minutes. The resulting surge raised the Trishuli by roughly nine metres in thirty minutes. Over a thousand people are confirmed dead and more than four thousand remain unaccounted for. **[E]**

Three properties of that event defeated every warning system covering Nepal:

| Property | Consequence |
|---|---|
| **It was not raining** | Every rainfall-driven forecast system — Google Flood Hub, GLOFAS, NASA LHASA v2, DHM's own bulletins — had no input signal at all **[E]** |
| **It began outside Nepal** | No transboundary hydro-meteorological data-sharing arrangement exists with China, so nothing upstream was observable **[E]** |
| **Gauges measure stage, not rate of rise** | Four of five downstream stations were destroyed by the surge before their absolute thresholds were crossed **[E]** |

The alert that did save lives was a **human phone call at about 09:00 NPT**, which triggered 679,295 SMS messages within one minute and evacuated a school of 1,643 students in Bidur. **[E]** The dissemination infrastructure worked. The trigger did not exist.

### The thesis

> The initiating mass movement produced a seismic signal strong enough that **USGS initially catalogued it as an M4.4 earthquake** before identifying it as landslide-generated. **[E]** That signal was public, on open FDSN data, minutes before the water reached the first settlements. Nobody was listening.

**GHADI listens.** It detects large mass-movement events in Himalayan headwaters from continuous seismic waveforms within seconds-to-minutes of initiation, corroborates the detection against an independent downstream river-gauge rate-of-rise anomaly, and emits a CAP-formatted alert into the SMS and siren infrastructure Nepal already operates.

### The one-line scope

**Detection, not prediction.** GHADI does not forecast when a slope will fail. It hears the slope fail and races the water downstream.

### Non-goals — write these on the wall

| Not building | Why |
|---|---|
| Earthquake prediction | Not scientifically possible. Geller et al. (1997) remains unrefuted; nothing in the ML literature claims otherwise **[E]** |
| A rainfall-driven flood forecast model | GLOFAS, Google Flood Hub and DHM/CBEWS already occupy that space, and the deaths this project targets are elsewhere **[I]** |
| A general "disaster AI platform" | Nepal has BIPAD. A parallel platform gets orphaned at the end of the funding cycle **[I]** |
| Public auto-alerting in v1 | Legally and ethically premature. See §9 deployment tiers and §12 |
| Anything requiring new field hardware in phase 1 | The primary data source is already free and already flowing **[V]** |

---

## 2. What has already been verified — read before planning

Everything in this section was established by running code against live services on **2 September 2026**. It is the difference between planning against assumptions and planning against facts.

### 2.1 The data exists and is free **[V]**

| Fact | Detail |
|---|---|
| Nepal has an open permanent broadband station on FDSN | **NK.KKN** — Kakani, Nepal. 27.800 °N, 85.279 °E, 2042 m. Guralp CMG-3T, three components (BHZ/BHN/BHE), **50 Hz**, operating since 2016-05-22, open-ended |
| Distance to the 2026 source zone | **55.9 km** — an excellent regional distance for a large mass-movement source |
| Waveform data for the event window is retrievable today | HTTP 200 from `service.iris.edu/fdsnws/dataselect` for 2026-08-26T02:43:30–03:18:30Z; 105,001 samples returned |
| Other stations within 4° | `IO.EVN` (Everest Pyramid Lab, 5010 m, **130.9 km** from the source), `NQ.KNSET` and `NQ.KTNP2` (strong-motion, Kathmandu Valley), `K5.WANG` (Bhutan). `SY.*` entries are **synthetics — must be excluded** |
| A reference-earthquake catalogue is available | USGS FDSN event service returned **108 candidate events** M≥4.3 within 4° of the source, 2024-01-01 to 2026-08-25 |

**Planning consequence:** the phase-1 critical path has **no procurement, no import clearance, no hardware, and no data-sharing agreement**. A developer can be productive on day one. This is unusual and should be exploited.

**Planning caveat:** Nepal's open broadband coverage is **one station**. Everything about localisation, redundancy and graceful degradation follows from that constraint. Do not design as though a network exists.

### 2.2 The signal is there — Experiment 001 result **[V]**

A first reconnaissance experiment was run on NK.KKN.BHZ across four cases: the 26 August 2026 cascade, two real regional earthquakes from the USGS catalogue recorded on the same station, and a quiet-noise window at the same clock time one week earlier (to control diurnal cultural noise). Analysis band 0.5–20 Hz.

| Case | Class | Emergence (s) | **LF/HF ratio** | Kurtosis | **Spectral centroid (Hz)** | Max STA/LTA |
|---|---|---:|---:|---:|---:|---:|
| **26 Aug 2026 Bhote Koshi** | mass movement | 46.6 | **13.65** | 90.6 | **1.44** | 16.68 |
| Reference EQ, 18 Aug 2026 | earthquake | 307.1 | 0.87 | 152.4 | 3.85 | 25.76 |
| Reference EQ, 19 Jul 2026 | earthquake | 31.0 | 4.74 | 210.9 | 3.19 | 27.29 |
| Quiet noise, 19 Aug 2026 | noise | 254.6 | 3.75 | 3.20 | 2.76 | 6.69 |

**Finding 1 — the signal is unambiguous.** SNR 85.2 dB, peak STA/LTA 16.7, a 67-second trigger window. The spectrogram shows a sharp onset followed by a low-frequency-dominated tail persisting for more than 25 minutes. **[V]**

**Finding 2 — the spectral discriminants separate cleanly, exactly as the physics predicts.** The cascade's low-to-high frequency energy ratio is **13.65**, against 0.87 and 4.74 for two real earthquakes and 3.75 for noise. Its spectral centroid is **1.44 Hz**, against 2.76–3.85 Hz for everything else. A spatially extended, slow, low-stress-drop source radiates low-frequency energy; a sharp tectonic rupture does not. That is the separation GHADI is built on, and it is present in real data on the first look. **[V]**

**Finding 3 — the timing is tighter than any published account.** The main trigger onset is at **02:52:24 UTC**. Correcting for roughly 15 s of travel time over 55.9 km puts source initiation at approximately **02:52:10 UTC = 08:37:10 NPT**. Published reports give only "~08:37–08:40". **[V]** This matters operationally: it is the anchor for every lead-time calculation the project will make.

**Finding 4 — a genuine negative result, and the most useful thing in the experiment.** The hand-specified composite score ranked **noise highest (0.823), above the actual target (0.726)**. Two defects cause this and both must be fixed before any model is trained:

- `emergence_s` is measured from 10% to 90% of the *global window peak*. When the peak is not the event, or when the window is noise with no true peak, the feature is meaningless — hence 307 s for an earthquake and 254 s for noise. **It must be redefined relative to the trigger onset, not the global maximum.**
- The `duration_ratio` term rewards energy spread evenly across the window, which is the definition of noise. It needs a signal-presence gate.

**Planning consequence:** budget a feature-engineering iteration (M2) *before* the classifier milestone. Do not let anyone skip from "the signal is there" to "train a model". **[I]**

**Finding 5 — a known artefact developers will hit immediately.** Every case produces a spurious trigger at exactly +60 s, because the 60-second LTA has not settled. **The first LTA-length of every window must be discarded.** Document it, test for it, and do not let it into a training set as a positive. **[V]**

### 2.3 What has *not* been verified

| Unknown | Why it matters |
|---|---|
| Whether NK.KKN latency supports **real-time** operation | Everything above is *archive* retrieval. Real-time requires SeedLink or equivalent, and the achievable latency is unmeasured. **This is the single most important unknown in the project** and is Milestone M0's first task |
| Whether DHM will provide gauge series at native sampling | The corroboration channel depends on it. See Blocker B2 |
| Whether the BIPAD portal exposes an API | Determines the integration path. See Blocker B1 |
| How many comparable Himalayan events have usable waveforms | Determines whether supervised learning is viable at all, or whether this stays a physics-based detector. See Risk R1 |

---

## 3. Success criteria

The project succeeds if, within 18 months, it can state — with published numbers — the answer to:

> **"On 26 August 2026, how many minutes of warning could this system have delivered to Timure, Syabrubesi and Bidur, and at what false-alarm rate per station-month?"**

Everything else is instrumental. Concretely:

| Level | Criterion |
|---|---|
| **Minimum viable result** | A retrospective detection of the 26 Aug 2026 event with a measured latency and a measured false-alarm rate on at least six months of continuous NK.KKN data. Publishable even if the FAR is too high to deploy |
| **Target result** | Detection latency ≤ 180 s at a false-alarm rate ≤ 1 per station-month, validated on held-out events, with an end-to-end lead-time figure for named settlements |
| **Deployment result** | The above, running in shadow mode at DHM through a full monsoon, emitting CAP into BIPAD |

**Falsification criteria — state these in the project charter.** The core hypothesis is dead if either: (a) mass-movement signals cannot be separated from noise and earthquakes on Nepal's sparse network at any useful false-alarm rate; or (b) detection latency exceeds surge travel time to the settlements at risk. Both outcomes are publishable, and a team that cannot say what would falsify its own project is running an advocacy exercise, not research. **[I]**

---

## 4. System architecture

```
   ┌──────────────────────── DETECTION PATH (latency-critical) ────────────────────────┐
   │                                                                                    │
   │  FDSN / SeedLink ──► preprocess ──► features ──► classifier ──┐                     │
   │  (NK.KKN, IO.EVN)    0.5–20 Hz      §5.2         calibrated   │                     │
   │                                                                │                    │
   │  DHM telemetry ────► rate-of-rise ──► robust-z anomaly ────────┤                    │
   │  (stage, native)     d(stage)/dt      median/MAD               │                    │
   │                                                                ▼                    │
   │                                                    ┌───────────────────────┐        │
   │                                                    │  FUSION               │        │
   │                                                    │  independence-grouped │        │
   │                                                    │  noisy-OR + cost-loss │        │
   │                                                    └───────────┬───────────┘        │
   │                                                                ▼                    │
   │                                            WATCH / ADVISORY / WARNING               │
   └────────────────────────────────────────────────────────────────┬───────────────────┘
                                                                    ▼
                                                   ┌────────────────────────────┐
                                                   │ HUMAN GATE (DHM duty desk) │
                                                   │ sees evidence, not a score │
                                                   └────────────┬───────────────┘
                                                                ▼
                          CAP 1.2 XML ──► BIPAD · mass SMS · sirens · FM · district EOC
                                                                │
   ┌──────────────── ANALYSIS PATH (not latency-critical) ───────┴───────────────┐
   │  satellite lake/slope monitoring · event catalogue · retrospective replay    │
   │  travel-time tables · exposure layers · post-event validation                │
   └─────────────────────────────────────────────────────────────────────────────┘

                      APPEND-ONLY AUDIT LOG spans every stage
```

### Four architectural rules, each with a reason

1. **The detection path and the analysis path are physically separate services.** In a disaster the analysis path will be down — that is when detection matters most. The detector must not import anything that can block on a satellite API. **[I]**
2. **Degradation is a first-class output, never a silent state.** Four of five gauges died on 26 August 2026. Every decision object carries `channels_alive` and `channels_dead`, and every alert says so in its text. A system that quietly loses a channel is worse than one that fails loudly, because it is confidently wrong. **[E→I]**
3. **Corroboration requires source *independence*, not agreement count.** Two channels fed by the same sensor are one channel. The fusion layer collapses independence groups before counting. **[I]**
4. **No generative model ever produces a number.** Numbers come from structured records; language models may only phrase them. This is a hard rule, enforced in code review. **[I]**

---

## 5. Module contracts

A reference implementation of the skeleton below already exists and runs (§2.2). Treat it as a starting point to be rewritten freely, not as a design to be preserved.

### 5.1 Module map

| Module | Responsibility | Latency budget | Status |
|---|---|---|---|
| `ghadi.config` | All tunable parameters in one place: bands, thresholds, cost ratio, CAP identity | — | skeleton exists |
| `ghadi.catalog` | The Himalayan Mass-Movement Seismic Event Catalogue. Every entry carries `origin_uncertainty_s` | — | 6 seed events |
| `ghadi.fdsn` | Cached waveform + metadata + reference-earthquake access. **Returns failures, never raises on one station being down** | n/a (archive); < 5 s (live) | skeleton exists |
| `ghadi.features` | Preprocess, envelope, discriminant feature extraction | **< 1 s per 240 s window, CPU** | needs M2 rework |
| `ghadi.detect.sta_lta` | The honest baseline every learned model must beat | < 100 ms | skeleton exists |
| `ghadi.detect.classify` | Trained, calibrated mass-movement classifier | **< 2 s** | **not started (M3)** |
| `ghadi.hydro` | Gauge rate-of-rise + robust-z anomaly; synthetic surge generator for testing | < 100 ms | skeleton exists |
| `ghadi.fusion` | Independence-grouped noisy-OR, cost-loss thresholds, tiering | < 50 ms | skeleton exists |
| `ghadi.cap` | CAP 1.2 XML emission with machine-readable provenance | < 50 ms | skeleton exists |
| `ghadi.travel` | Surge travel-time tables per river reach → arrival estimates per settlement | — | **not started (M4)** |
| `ghadi.service` | Real-time loop, health monitoring, audit log | — | **not started (M5)** |

**End-to-end latency target: source initiation → CAP message ready ≤ 180 s**, of which the seismic wave itself consumes ~15 s over 56 km and data transport is the dominant unknown (§2.3).

### 5.2 The feature contract

Features exist to encode one physical difference each. Developers must be able to say which.

| Feature | Physical basis | Earthquake | Mass movement |
|---|---|---|---|
| `emergence_s` | Extended slow source ramps up; rupture jumps | small | large |
| `kurtosis` | Impulsiveness of the amplitude distribution | high | low |
| `spectral_ratio_low_high` | Low-stress-drop extended source is LF-depleted at HF | low | **high** |
| `spectral_centroid_hz` | Same, expressed as a first moment | higher | **lower** |
| `duration_80_s`, `duration_ratio` | Long-duration mass flux vs short body-wave train | low | high |
| `rise_to_duration` | Shape of the envelope, scale-free | small | large |
| `max_sta_lta` | Baseline detector response | high | moderate |

**As of Experiment 001 the two spectral features carry almost all the separation and the two temporal features are broken.** Fixing the temporal features is M2; it is not optional, because a classifier trained on two correlated spectral features will overfit and will not generalise to a smaller event. **[V→I]**

### 5.3 Hard interface rules

- Every timestamp is timezone-aware UTC. Nepal Standard Time is **UTC+05:45** — an unusual offset that will be got wrong at least once; put it in a test.
- Every catalogue entry carries `origin_uncertainty_s`. **Zero is forbidden** for any event whose time came from a news report.
- Every probability is calibrated and reported with an interval. A bare scalar with no uncertainty must not appear in an operational output.
- Every alert records the exact model version that produced it.

---

## 6. Data contracts

### 6.1 Seismic

| Field | Value |
|---|---|
| Source | FDSN `dataselect` (archive) / SeedLink (real-time) |
| Provider | EarthScope, formerly IRIS. ObsPy's `Client("IRIS")` now emits a deprecation warning — **use `"EARTHSCOPE"`** |
| Primary station | `NK.KKN..BHZ`, 50 Hz, Guralp CMG-3T |
| Secondary | `IO.EVN` (130.9 km), `NQ.KNSET`, `NQ.KTNP2` (strong-motion, Kathmandu) |
| **Exclusions** | `SY.*` are **synthetic** and must be filtered out of every query |
| Caching | Content-addressed MiniSEED under `data/cache`, keyed by NSLC + window. A second run must be offline and byte-identical |
| Licence | Open |

### 6.2 Hydrological — **not yet available, design against the interface**

The detector takes a plain `(times_s, stage_m)` pair, deliberately, because DHM telemetry access is an open negotiation (Blocker B2). Swap the loader, keep the detector.

Reference figure for calibration: the Trishuli rose **~9 m in 30 minutes**, i.e. ~0.30 m/min sustained, with a far steeper leading edge. The default absolute threshold of **0.20 m/min** sits below that. **[E]**

The synthetic generator must support `destroy_at_s`, which truncates the series to simulate sensor mortality. Every hydro detector is tested against a destroyed sensor, because that is what actually happened.

### 6.3 The event catalogue schema

```yaml
event_id:                  NPL-2026-08-26-BHOTEKOSHI-001
origin_utc:                2026-08-26T02:53:30Z    # refine to 02:52:10 per Finding 3
origin_uncertainty_s:      180                     # NEVER zero for a news-derived time
label:                     mass_movement           # | earthquake | noise | unknown
lat, lon:                  28.255, 85.520
location_uncertainty_km:   8.0
hazard_subtype:            ice_rock_avalanche_dam_break
river_system:              "Lhende Khola -> Bhote Koshi -> Trishuli"
deaths:                    1058
deaths_status:             PROVISIONAL             # CONFIRMED | PROVISIONAL | ESTIMATE
sources:                   [ url, ... ]
```

### 6.4 Split policy — the part most disaster-ML work gets wrong

Three rules, to be stated in every paper and enforced in code:

1. **Event holdout.** Hold out entire events. A model that has seen half the 26 August window will trivially classify the other half.
2. **Temporal holdout.** Train on the past, test on the future, because that is the deployment condition.
3. **Station-configuration holdout.** Evaluate with stations removed. One-station operation is the normal case in Nepal, not the degraded case.

Random windowed splits are forbidden. They will produce a beautiful, meaningless number. **[I]**

---

## 7. Milestones

| ID | Milestone | Duration | Exit criteria — all must be demonstrable, not asserted |
|---|---|---|---|
| **M0** | **Access and latency truth** | 3 weeks | Real-time NK.KKN latency measured and documented. Letters sent to NDRRMA, DHM and DMG/NEMRC. BIPAD API question answered yes or no |
| **M1** | **Catalogue and corpus** | 6 weeks | ≥ 6 labelled positive windows, ≥ 100 reference earthquakes, ≥ 6 months of continuous noise, all cached and reproducible. Split policy implemented and tested |
| **M2** | **Feature rework** | 4 weeks | `emergence_s` redefined relative to trigger onset; LTA settling artefact removed; every feature has a documented physical basis and a unit test; separation quantified with confidence intervals |
| **M3** | **Classifier + calibration** | 8 weeks | A calibrated model that **beats STA/LTA on the emergent class**, with ROC, reliability diagram, and a stated operating point under a published cost ratio. If it does not beat the baseline, that is the deliverable |
| **M4** | **Fusion, travel time, CAP** | 6 weeks | Travel-time tables for ≥ 3 river reaches; fusion tested under 1-, 2- and 3-channel loss; valid CAP 1.2 output validated against the schema |
| **M5** | **Retrospective replay** | 6 weeks | **The headline result:** for each catalogue event, what the system would have produced and when, using only data available at that moment. Lead-time figures for named settlements |
| **M6** | **Shadow deployment** | 1 monsoon | Continuous shadow operation at DHM. Published false-alarm rate per station-month. No public alerting |

Milestones overlap; the serial critical path is **M0 → M1 → M2 → M3 → M5**. M4 can run in parallel with M3.

---

## 8. Issue-level backlog

Ready to be pasted into a tracker. Sizes: **S** ≤ 2 days, **M** ≤ 1 week, **L** ≤ 3 weeks.

### M0 — Access and latency truth
| # | Issue | Size |
|---|---|---|
| 0.1 | **Measure real-time NK.KKN latency.** Connect over SeedLink, log arrival delay per packet for 7 days, publish the distribution. *This determines whether the project is viable in real time at all* | M |
| 0.2 | Draft and send three letters: NDRRMA (BIPAD API + incident records), DHM (gauge series at native sampling + CAP SOP status), DMG/NEMRC (waveform access, station metadata, collaboration) | S |
| 0.3 | Switch the FDSN client from `IRIS` to `EARTHSCOPE`; add a `SY.*` exclusion filter with a test | S |
| 0.4 | Confirm the current legal status of Nepal's data-protection framework with counsel before any personal-data work is scoped | S |
| 0.5 | CI: lint, type-check, unit tests, and a network-free test mode using cached fixtures | M |

### M1 — Catalogue and corpus
| # | Issue | Size |
|---|---|---|
| 1.1 | Expand the catalogue beyond the 6 seed events; search literature and news for Himalayan mass movements 2016–2026 with plausible seismic records | L |
| 1.2 | Harvest ≥ 100 reference earthquakes from the USGS catalogue within 4° and fetch their NK.KKN windows | M |
| 1.3 | Harvest ≥ 6 months of continuous noise, **stratified by season and hour** so the model cannot learn a monsoon-noise shortcut | M |
| 1.4 | Implement event / temporal / station-configuration splits with tests that fail on random splitting | M |
| 1.5 | Investigate the Gorkha co-seismic landslide population (4,312+ mapped) as a positive source — signals sit inside the mainshock coda, which is a research problem in itself | L |
| 1.6 | Data card documenting provenance, class balance, and known gaps | S |

### M2 — Feature rework
| # | Issue | Size |
|---|---|---|
| 2.1 | **Redefine `emergence_s` relative to trigger onset**, not global peak. Regression-test against the four Experiment 001 cases | M |
| 2.2 | Discard the first LTA-length of every window; assert no trigger survives at `+lta_s` | S |
| 2.3 | Gate `duration_ratio` on signal presence so diffuse noise cannot score high | S |
| 2.4 | Add instrument-response deconvolution so features are in physical units and comparable across stations | M |
| 2.5 | Add three-component features (BHZ/BHN/BHE): polarisation, H/V ratio. Mass flows and tectonic sources partition energy differently between components | M |
| 2.6 | Quantify separation per feature with bootstrap confidence intervals; **delete features that do not separate** | M |

### M3 — Classifier
| # | Issue | Size |
|---|---|---|
| 3.1 | Establish the STA/LTA baseline on the full corpus with a published ROC. Everything is measured against this | M |
| 3.2 | Gradient-boosted trees on the engineered features; nested CV under the split policy | M |
| 3.3 | Spectrogram CNN as the learned-representation arm | L |
| 3.4 | Probability calibration (isotonic or Platt) with reliability diagrams | S |
| 3.5 | Cost-loss operating-point selection with a **published** cost ratio and a sensitivity analysis | M |
| 3.6 | **Delete `Features.mass_movement_score`.** It is a transparent placeholder that Experiment 001 showed ranks noise above the target; it must not survive into a model release | S |

### M4 — Fusion, travel time, CAP
| # | Issue | Size |
|---|---|---|
| 4.1 | Travel-time tables for Lhende–Bhote Koshi–Trishuli, Sun Koshi, Tamakoshi; calibrate against the 2026 event's observed ~9 m/30 min progression | L |
| 4.2 | Fusion tests under 1-, 2- and 3-channel loss, asserting that tier degrades rather than the system failing silently | M |
| 4.3 | Validate CAP output against the OASIS 1.2 schema; add a test that `status != "Actual"` outside an explicitly authorised build | S |
| 4.4 | Nepali alert text from a **strict template** — numbers injected from structured records only, never generated | M |
| 4.5 | Exposure join: WorldPop + VIDA building footprints + 2021 census ward aggregates per river reach | M |

### M5 — Replay
| # | Issue | Size |
|---|---|---|
| 5.1 | Replay harness that presents only data available at each simulated moment (strict causality; no lookahead) | L |
| 5.2 | **The headline analysis:** lead time delivered at Timure, Syabrubesi and Bidur for the 26 Aug 2026 event | M |
| 5.3 | False-alarm rate per station-month over the continuous noise corpus | M |
| 5.4 | Paper draft: detection science | L |

---

## 9. Deployment tiers

Most disaster-AI projects fail by attempting tier T2 on day one. The tiering **is** the adoption strategy.

| Tier | Automated | Gate | Promotion condition |
|---|---|---|---|
| **T0 Shadow** | Everything; no alert leaves the system | none | From day one |
| **T1 Advisory to officials** | Alert reaches DHM/NDRRMA/district EOC staff only | human forwards | One monsoon of T0 at an acceptable FAR |
| **T2 Human-approved public alert** | Message drafted, CAP formed, dissemination pre-staged; a human presses send | duty officer | Documented T1 performance |
| **T3 Auto-fire, top tier only** | Highest-confidence corroborated detections fire automatically | post-hoc review | **Explicit NDRRMA authorisation and a legal basis** |

**A model may not be promoted without a completed shadow period of at least one full monsoon.** Put it in the definition of done.

---

## 10. Team and skills

| Role | FTE | Notes |
|---|---|---|
| Seismology / signal processing | 1.0 | **The critical path.** ObsPy, FDSN, time-series ML. This hire determines the schedule |
| Backend / platform engineer | 1.0 | Real-time services, caching, MLOps, audit logging, CI |
| Geospatial / hydrology | 0.5 | Travel-time tables, exposure joins, river-reach modelling |
| Research lead / PI | 0.5 | Method, publication, falsification discipline |
| **Government liaison** | 0.25 | **The highest-leverage quarter-FTE in the plan.** Half the project is gated on §11 |

Indicative 18-month cost: **USD 45–80 k** excluding institutional overhead and excluding any gauge-instrumentation pilot (which would add USD 20–40 k).

---

## 11. Blockers and external dependencies

Each has a named owner and an action. Blockers B1–B3 should be actioned in **week one**; none of them is a research question, and half the programme is gated on the answers.

| ID | Blocker | Owner | Action | If refused |
|---|---|---|---|---|
| **B1** | Does BIPAD expose an API? Not verifiable from outside; no public docs or repo located | Liaison → NDRRMA | Letter + meeting | Integrate via CAP file drop; treat BIPAD as write-only |
| **B2** | DHM gauge series at native sampling | Liaison → DHM | Data-sharing agreement | **Ship the seismic-only detector.** Fusion is deferred, not cancelled — design so a refusal delays a feature rather than killing the project |
| **B3** | Waveform collaboration and station metadata | Liaison → DMG/NEMRC | Letter + meeting | Archive FDSN access already suffices for M1–M3; only real-time SeedLink is at risk |
| **B4** | Real-time latency (issue 0.1) | Seismology | Measure it | If latency > ~120 s, the project becomes retrospective-analysis-only and must be re-scoped honestly |
| **B5** | Upstream Tibetan data | Government-to-government | Out of scope for the team | **This is why GHADI exists.** The project's whole premise is inferring the upstream event without the agreement |
| **B6** | Legal basis for automated alerting | Liaison + counsel | Early clarification with NDRRMA | The DRRM Regulations bar transmitting information that "may create unnecessary panic or fear" **[E]**. Resolve at T1, not at T3 |

---

## 12. Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R1** | **Too few labelled positive events to train on.** Large well-recorded Himalayan cascades are rare, and NK.KKN only starts in 2016 | High | High | Exploit the Gorkha co-seismic landslide population; use physics-based features that need few examples; accept that the deliverable may be a well-characterised physics detector rather than a learned one — which is still publishable and still deployable |
| **R2** | False alarms destroy institutional trust | Medium | High | Corroboration requirement; tiered deployment; published cost ratio; long shadow period |
| **R3** | Real-time latency too high (B4) | Medium | High | Measure in week one, before anything else is built |
| **R4** | Single-station fragility — one station, and it can fail | Medium | Medium | Graceful degradation designed in from the start; secondary stations; explicit degraded-mode alert text |
| **R5** | Overfitting to one event | High | High | Split policy; leave-one-event-out evaluation; report per-event performance, never pooled |
| **R6** | Donor-project death after funding ends | Medium | High | Government co-ownership from day one; open source; an O&M line with a named government budget code — NDRRMA will ask, having absorbed CBEWS from Practical Action **[E]** |
| **R7** | Scope creep into a general disaster platform | High | Medium | The non-goals table in §1. Re-read it at every planning meeting |

---

## 13. Definition of done and quality bar

**Code.** Type hints on public functions. Docstrings that state *why*, not what. Unit tests for every feature and every threshold. A network-free test mode using cached fixtures. CI green before merge.

**Research.** No parameter is tuned on the test set — and the split policy is enforced in code, not in good intentions. Every reported number carries an uncertainty. Every experiment is re-runnable from a cold cache with one command. Negative results are committed, not deleted: Experiment 001's failure of the composite score is in the repository, and that is the standard.

**Operations.** Append-only audit log recording input hash, model version, score, gate decision, operator identity and dissemination result. Every output states which channels were alive. Nothing fails silently.

**Documentation.** Every merged milestone updates this handoff. An ADR for every architectural decision that a future developer would otherwise reverse by accident.

---

## 14. Repository layout

```
ghadi/
├── README.md                    project statement, quickstart, the one-line scope
├── docs/
│   ├── HANDOFF.md               this document
│   ├── ARCHITECTURE.md          the diagram in §4, expanded
│   ├── DATA_SOURCES.md          every source, licence, access status
│   ├── EXPERIMENTS.md           index of experiments and their findings
│   └── decisions/               ADRs
├── src/ghadi/
│   ├── config.py                all tunables in one place
│   ├── catalog.py               the event catalogue
│   ├── fdsn.py                  cached waveform + metadata access
│   ├── features.py              discriminant features
│   ├── detect/
│   │   ├── sta_lta.py           the honest baseline
│   │   └── classify.py          the learned detector (M3)
│   ├── hydro.py                 rate-of-rise anomaly
│   ├── fusion.py                corroboration + cost-loss
│   ├── travel.py                surge travel-time tables (M4)
│   ├── cap.py                   CAP 1.2 emission
│   └── service.py               real-time loop (M5)
├── experiments/
│   └── exp001_signal_recon/     run.py · results.json · figures/ · FINDINGS.md
├── data/
│   ├── cache/                   gitignored; content-addressed MiniSEED
│   └── catalog/                 committed event definitions
├── tests/
└── .github/workflows/ci.yml
```

**Conventions.** `main` is always green. Branch per issue, named `m2/emergence-rework`. Commits explain why. Experiments are immutable once run — a new question gets a new experiment directory, never an edit to an old one.

---

## 15. Non-negotiable safety rules for developers

1. **`status` must never be `Actual` and `scope` must never be `Public`** in any non-authorised build. There is a test for this. Do not skip it.
2. **No generative model produces a number.** Templates only, with values injected from structured records.
3. **No personal data** — hotline transcripts, missing-person records, mobility data — enters this repository without a signed agreement and a separate access-controlled store. The seismic and hydrological work needs none of it.
4. **Never delete a negative result.**
5. **Never report a pooled metric** where a per-event or per-district metric would reveal a failure.
6. **Never claim prediction.** The word in every document, commit message and paper is *detection*.

---

## 16. Open questions for the lead

1. Is the team prepared to publish a null result if M3 shows the classifier cannot beat STA/LTA on emergent signals? The answer shapes the incentive structure for everyone below.
2. Does the institutional home sit at NDRRMA, DHM, or a university with an MoU? This determines who owns the audit log and who is accountable for a false alarm.
3. Is there appetite to fund a single gauge-instrumentation pilot (native-sampling telemetry on one upper Trishuli station)? It would convert Blocker B2 from a negotiation into an asset.
4. Should the repository be public from day one? Open science aids credibility with ICIMOD and NDRRMA; it also means a half-finished detector is visible. All the underlying data is open regardless.
5. Who signs the letters in issue 0.2? They will be more effective over an institutional signature than a researcher's.

---

## Appendix A — Glossary

| Term | Meaning |
|---|---|
| **CAP** | Common Alerting Protocol, OASIS 1.2. The interoperability standard DHM began adopting with WMO in April 2025 |
| **FDSN** | International Federation of Digital Seismograph Networks — the open standard and web services for seismic data |
| **GLOF** | Glacial Lake Outburst Flood |
| **LTA / STA** | Long-term / short-term average. The classical seismic detector |
| **MiniSEED** | The standard seismic waveform interchange format |
| **NSLC** | Network.Station.Location.Channel — the seismic identifier, e.g. `NK.KKN..BHZ` |
| **NPT** | Nepal Standard Time, **UTC+05:45** |
| **PDGL** | Potentially Dangerous Glacial Lake |
| **Emergent onset** | An arrival whose amplitude ramps up gradually — the mass-movement signature — as opposed to an impulsive tectonic arrival |

## Appendix B — Reference figures for calibration

| Quantity | Value | Source |
|---|---|---|
| Source zone (2026 event) | ~28.255 °N, 85.520 °E, inside TAR/China | **[E]** |
| Source-to-NK.KKN distance | **55.9 km** | **[V]** |
| Seismic onset at NK.KKN | **02:52:24 UTC** | **[V]** |
| Inferred source initiation | **≈02:52:10 UTC = 08:37:10 NPT** | **[V]** |
| Trishuli rise | ~9 m in 30 min (~0.30 m/min sustained) | **[E]** |
| SMS dissemination capacity, demonstrated | 679,295 messages in 1 minute | **[E]** |
| Bidur school evacuation, achieved on informal notice | 1,643 students in ~14 minutes | **[E]** |
| Estimated surge travel time to first settlements | 20–40 minutes | **[E]** |
| **Therefore: achievable warning at T+3 min dissemination** | **17–37 minutes** | **[H]** |

That last row is the project. Everything else is how to earn the right to claim it.
