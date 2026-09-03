# Experiment 008 — Can the positive class grow beyond n = 1?

**Question.** exp007 showed five catalogue events have waveform data but no labelled
window, because their origin times are news-derived with uncertainties of minutes to
hours. Is there a findable signal inside those windows?

**Answer: no, not from this evidence. The positive class stays at n = 1.** The
experiment's value is in what it rejected, and in showing *why* the method cannot work
for the events that matter most.

Run 2026-09-02. Search windows: reported origin ± (uncertainty + 15 min).

## Design, and the circularity it avoids

Using the mass-movement spectral criteria to *find* positives and then evaluating those
criteria on what they found would be circular — it would manufacture a corpus that
agrees with the detector by construction. So:

- **Selection is class-agnostic**: STA/LTA triggers with peak ratio ≥ 6, nothing more.
- **Corroboration never touches the features**: cross-station timing consistency, plus
  exclusion of catalogued teleseisms.
- **Spectral features are read out last**, never used to select.

## Result

| Event | IO.EVN triggers | NK.KKN triggers | Candidates | Expected by chance |
|---|---:|---:|---:|---:|
| Jure 2014 | 4 | *no data* | 0 | 0.0 |
| Langtang/Gorkha 2015 | 4 | *no data* | 0 | 0.0 |
| Melamchi 2021 | 43 | 4 | **2** | 0.5 |
| Thame 2024 | 9 | **0** | 0 | 0.0 |
| Rasuwagadhi 2025 | 9 | 2 | 0 | 0.1 |

**Nothing here is strong enough to label.** Melamchi's two survivors sit at the edge of
the lag tolerance against 0.5 expected by chance — an excess of 1.5 events, which is not
evidence.

## The rejection that justifies the method

The first version of the cross-station test asked only that the two stations' triggers
be *close in time* (within 120 s). Under that rule Rasuwagadhi 2025 produced an
apparently strong candidate: IO.EVN and NK.KKN both triggering near 03:53:44 with peak
ratios 11.9 and 11.8, against 0.5 expected by chance.

It is physically impossible.

| Station | Distance to source | Trigger |
|---|---:|---|
| IO.EVN | 130 km | 03:53:44.3 |
| NK.KKN | **62 km** | 03:54:01.5 |

**The nearer station fired 17 s later.** A single source at Rasuwagadhi must reach
NK.KKN *first*, by 11–19 s depending on apparent velocity. The observed lag is ~30 s
wrong, in the wrong direction. Two unrelated local transients, not one event.

The test now requires the lag to match the lag the event location predicts — **in sign
as well as size** — and the pair is correctly rejected. Chance rate is computed against
the width of the accepted lag band rather than an arbitrary tolerance.

**A "small time difference" is not corroboration.** It is satisfied by any two unrelated
transients in a busy window, and busy windows are exactly what a multi-hour search
produces. Requiring physical consistency is what makes cross-station agreement mean
something, and it is cheap.

## The structural limitation: this fails where it is most needed

Cross-station corroboration was unavailable for three of the five events, for two
different reasons, and neither is fixable by tuning:

1. **Jure 2014 and Langtang 2015: NK.KKN has no data at all.** IO.EVN alone cannot
   corroborate itself. These are exactly the events the handoff most wants (the Gorkha
   co-seismic population), and they are reachable on one station only.
2. **Thame 2024: the event was too small to reach the second station.** IO.EVN, 21 km
   away, produced 9 triggers. NK.KKN, 132 km away, produced **zero**. A small GLOF is
   detectable near and invisible far.

**Point 2 is the one that matters beyond this experiment.** Small events — the ones a
detector most needs training examples of, and the ones a warning system would ideally
catch early — are single-station events by nature. Any corroboration scheme built on
station agreement is structurally blind to them. It works for large events, which are
the ones least in need of help.

That is the same argument the handoff makes for corroborating with an *independent
channel* rather than a second seismometer (rule 3, `ghadi.fusion`): a downstream gauge
sees the water regardless of how the seismic energy attenuated. On this evidence the
gauge channel is not a nice-to-have for false-alarm control — it is the only
corroboration available for the small end of the event distribution. Blocker B2 is
more central than its position in the risk table suggests.

## Where the positive class actually has to come from

Not from this method. The realistic routes, in order of cost:

1. **Human adjudication against published accounts.** The candidates here are timestamps
   for a domain expert to check against reported observations — Melamchi's chain in
   particular is documented in ICIMOD's reconstruction with sub-hour detail this
   experiment did not use.
2. **Satellite-derived timing bounds**, which is how the Gorkha co-seismic inventories
   were built and how the handoff proposes to anchor labels (issue 1.5).
3. **Accepting single-station labels for near-field events**, with the honesty that they
   carry no independent corroboration and must be flagged as such in the data card.

## What this experiment cannot show

- Absence of signal is not demonstrated. A signal below peak ratio 6, or outside the
  reported uncertainty window, would not have been found. The Melamchi search covered
  6.5 h around a reported time that may itself be wrong.
- Only two stations were searched. NQ.KNSET and NQ.KTNP2 hold some of these events and
  were not included; adding them would give a third constraint and is the obvious
  extension.
- The features quoted during diagnosis were computed over 30-minute chunks, not
  decision-time segments, so they are indicative only (exp005 established segments are
  the correct basis).
