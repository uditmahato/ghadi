# Experiment 032: do thresholds set from each station's own earthquakes carry over?

**Question.** exp031 found that the 2017 Bondo rock avalanche sits in the low frequency
tail of its own region's earthquakes, but the Nepal thresholds pass it at only one
Swiss station of five. Would a rule set relative to each station's own earthquakes
carry between networks? Such a rule calls a segment mass movement like when its LF/HF
is above a chosen quantile of that station's earthquakes and its centroid is below the
matching lower quantile.

**Answer.** It carries, at a price. At the 0.80 quantile the relative rule passes six of
seven station records of the two events: both Nepal stations for 2026, and four of five
Swiss stations for Bondo. The absolute rule passes three. It lets through about the
same share of earthquakes as the absolute rule does on NK.KKN, 16 to 22 percent on every
station. At NK.KKN it raises fewer noise alarms than the absolute rule, 27 a month
against 34. On IO.EVN it raises three times as many, 349 a month against 110, because
the 2026 event was so extreme there that IO.EVN's absolute threshold sits far beyond
any quantile of its earthquakes. A relative rule throws that margin away.

Run 2026-10-14, offline: the Nepal corpora from the cache, the Swiss values from exp031.

## Results

Seven station records: the 2026 event on NK.KKN (64 earthquakes) and IO.EVN (132), and
Bondo on five Swiss stations (46 to 50 each). The earthquake share is the fraction of
that station's earthquakes the rule passes, each judged against quantiles computed
without it. Noise is false alarm windows per station month on the noise corpora, at the
spectral layer only (exp018 and exp022's basis, before the H/V, partner and catalogue
rules).

| Rule | Records passed | Earthquake share, NK.KKN | IO.EVN | Swiss stations | Noise, NK.KKN | IO.EVN |
|---|---:|---:|---:|---|---:|---:|
| Absolute (2026 values, 20% margin) | **3 of 7** | 22% | 6% | 0 to 20% | 34 | 110 |
| Relative, quantile 0.70 | 6 of 7 | 27% | 26% | 26 to 29% | 41 | 508 |
| Relative, quantile 0.75 | 6 of 7 | 23% | 23% | 22 to 25% | 34 | 438 |
| **Relative, quantile 0.80** | **6 of 7** | 20% | 16% | 16 to 22% | 27 | 349 |
| Relative, quantile 0.85 | 4 of 7 | 16% | 14% | 12 to 16% | 14 | 294 |
| Relative, quantile 0.90 | 3 of 7 | 11% | 9% | 7 to 12% | 14 | 208 |
| Relative, quantile 0.95 | 1 of 7 | 5% | 5% | 2 to 8% | 7 | 98 |

The absolute rule's NK.KKN and IO.EVN noise rates are exactly exp022's at the 20 percent
margin (34.22 and 110.23), which checks that this experiment rebuilds the same segments.

Which records pass:

| Station | Absolute | 0.75 | 0.80 | 0.85 | 0.90 |
|---|---|---|---|---|---|
| NK.KKN, 2026 | pass | pass | pass | fail | fail |
| IO.EVN, 2026 | pass | pass | pass | pass | pass |
| CH.VDL, Bondo | fail | pass | pass | pass | pass |
| CH.DAVOX, Bondo | fail | fail | fail | fail | fail |
| CH.MUGIO, Bondo | fail | pass | pass | pass | pass |
| CH.MMK, Bondo | fail | pass | pass | pass | fail |
| CH.SGT05, Bondo | pass | pass | pass | fail | fail |

## What it shows

* **A relative rule is how the method would move to a new network.** Set at the 0.80
  quantile it passes Bondo at four Swiss stations, enough for two station agreement,
  while letting through the same one in five earthquakes the Nepal rule does at NK.KKN.
  The absolute values could not have done that: they are one event's numbers.
* **For Nepal it is not an improvement.** At NK.KKN the two rules are close (0.80 is a
  little stricter on noise, 27 against 34 a month). At IO.EVN the absolute rule is far
  better, because the 2026 event stood so far out there. Replacing it would triple the
  station's spectral false alarms.
* **NK.KKN's 2026 event is not far into its own tail.** It fails the relative rule from
  0.85 up. On the station the live service decides on, the event sits about where one
  earthquake in five sits. That is the same overlap exp005 measured, seen from the other
  side, and a reason the other rules exist.
* **DAVOX fails every rule.** Its trigger fired on the first arrival (exp031), and its
  segment is not low frequency enough under any rule. A rule cannot fix an onset problem.

## What it does not show

* **The quantile was chosen after seeing Bondo.** The sweep is the result, not 0.80. A
  new network would set its quantile on its own noise and earthquakes, and then test it.
* **Two events, seven records.** "Six of seven" is not a detection probability.
* **No Swiss noise corpus.** The Swiss columns have earthquakes only; the cost on noise
  there is unknown.
* **Spectral layer only.** The deployed system adds the H/V rule (which exp031 showed does
  not carry over), the partner station and the catalogue. The full system rates are
  exp027's.

## What this means

* The Nepal deployment keeps its absolute thresholds.
* A deployment on a new network starts from a relative rule near the 0.80 quantile of
  that network's own earthquakes, measures its noise rate, and then sets its margin. It
  must not start from the Nepal values.
* The paper can say how the method would transfer, with numbers, and that the transfer
  has a cost.

## Design

`run.py`: the Nepal earthquake segments are recomputed from the cache exactly as exp010
does (onset from the committed corpus, 120 s segment, `ghadi.features.spectral_features`);
the Nepal noise segments come from the committed IO.EVN corpus and, for NK.KKN, from
`scripts/harvest_noise.py`'s `process` over the cache, as exp018 does. The Swiss values
are read from exp031's `results.json`. Quantiles are `numpy.quantile` over each station's
own earthquakes; an earthquake's own pass is judged with it left out.
