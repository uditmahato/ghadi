# Experiment 010 — Does the spectral separation reproduce on a second station?

**The question this settles.** Every separation result so far is from NK.KKN. A real
objection stood behind all of them: is the cascade's low-frequency character a property
of the *source* (a slow extended source is low-frequency wherever you stand), or of
*NK.KKN's site* — its response, geology, local noise? One station cannot tell them apart,
and if it were a site effect the project's premise would be unfounded.

**Answer: it reproduces, and more strongly. On IO.EVN — an independent station 131 km
from the source — the cascade sits even further into the low-frequency tail of the
earthquake population than it does on NK.KKN. The separation is source physics, not an
NK.KKN artefact.** This is the strongest positive result in the project so far, and the
caveats below keep it from being read as more than it is.

Run 2026-09-06. Method: exactly exp005's (120 s decision-time segments from the picked
onset), on IO.EVN.

## Results

| | NK.KKN (exp005) | IO.EVN (this) |
|---|---|---|
| Distance to source | 55.9 km | 131 km |
| Earthquake corpus (usable) | 64 | **132** |
| Cascade LF/HF | 4.14 | **15.07** |
| Cascade centroid | 2.04 Hz | **1.53 Hz** |
| Earthquake median LF/HF | 1.48 | 2.22 |
| Earthquake median centroid | 3.11 Hz | 2.67 Hz |
| **Earthquake overlap (both criteria)** | **17.2%** | **4.5%** (6/132) |

## Reading it correctly

**The separation is real physics.** The cascade is the lowest-frequency thing in the
population on *both* stations, and on the farther station it is *more* so. That is the
signature of source physics compounded by attenuation: over 131 km the high frequencies
are stripped harder, pushing both the cascade and the earthquakes toward lower frequency
— but the cascade, already low-frequency at source, stays ahead. A site effect would not
travel to a different station 75 km away; this did.

**The 4.5% is not simply "better than 17.2%".** The cascade's own values are far more
extreme on IO.EVN (LF/HF 15 vs 4), so the threshold it sets is more stringent, and
fewer earthquakes clear it partly for that reason. The honest statement is not "IO.EVN
discriminates 4× better" but "**the cascade remains distinctively low-frequency on an
independent station, at the tail of the earthquake distribution on both**." Both numbers
are lower bounds fitted to one event (the exp003 caveat still holds).

**IO.EVN has the near-field coverage NK.KKN lacked.** 60 of 132 events within 100 km,
110 within 200 km — against NK.KKN's 1 within 100 km. So this is also a genuinely better
earthquake corpus for anything distance-sensitive, and it is why the distance confound
below is now visible where NK.KKN could not see it.

## Confounds, re-checked (exp003 flagged magnitude on NK.KKN)

| Rank correlation | NK.KKN (exp003) | IO.EVN (this) |
|---|---|---|
| LF/HF vs magnitude | +0.44 | **+0.26** |
| Centroid vs magnitude | −0.42 | **−0.31** |
| LF/HF vs distance | +0.04 | **+0.25** |
| Centroid vs distance | +0.03 | **−0.29** |

Two things. The **magnitude confound is real but weaker** here, so the overlap is not
merely a size effect — the separation survives it on both stations. And **distance now
shows a confound** (it was invisible on NK.KKN only because that corpus had almost no
near-field events). This vindicates exp003's caution that its distance null "should not
be trusted far", and it means a classifier must control for distance as well as
magnitude — issue for M3.

## What this does NOT do

- **It does not grow the positive class.** This is the *same physical event* seen from a
  second station, not a second event. The positive class is still **n = 1**. What
  changed is that the one positive is now corroborated across two independent stations,
  which is evidence about the *feature*, not about the *population*.
- **Absolute LF/HF remains implementation- and distance-sensitive** (4.14 vs 15.07 for
  one event). exp001 already established the ratio is meaningless without its split
  frequency; this adds that it is meaningless without the station and distance too. Only
  the *ordering* — cascade at the low-frequency tail — is portable, and it is the
  ordering that reproduced.
- The two features are still one physical idea (exp003). A second station does not make
  them independent; three-component polarisation (issue 2.5) is still the route to an
  independent axis.
- IO.EVN's own false-alarm rate is unmeasured. A rate is per station (exp007); this
  experiment is about separation, not false alarms.

## Why it matters

The single most serious internal challenge to GHADI's premise was "maybe NK.KKN just
has a convenient site response." That challenge is now answered with data: the
discriminant is a property of the source, observed independently 75 km apart. The core
hypothesis — that mass movements are spectrally distinguishable from earthquakes —
survives its hardest test. It remains true that doing so *at a usable false-alarm rate*
is unproven, and that the positive class is one event.
