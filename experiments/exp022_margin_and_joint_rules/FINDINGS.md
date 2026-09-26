# Experiment 022: what does margin cost, and what do the rules remove together? (#32, #37)

**Question.** Every threshold so far is the 2026 event's own value, which has no margin.
Two new rules were priced one at a time. What is the false alarm rate when the
thresholds are loosened by a stated margin, and when the rules are applied together?

**Answer.** Margin on the spectral test is expensive on its own and cheap once the other
two rules are in force. With a 20 percent margin, the horizontal to vertical rule, and
a partner station whose trigger time fits a source in the basin box, NK.KKN gives no
false alarms in its corpus and IO.EVN gives about 6 per station month.

False alarms per station month. "2st" is a fitting trigger at the other station.

| Margin | NK.KKN spectral | + H/V | + 2st basin | + H/V + 2st basin | IO.EVN spectral | + H/V | + 2st basin | + H/V + 2st basin |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 13.7 | 0.0 | 0.0 | **0.0** | 88.8 | 18.4 | 9.2 | **6.1** |
| 10% | 27.4 | 3.4 | 0.0 | **0.0** | 101.1 | 27.6 | 9.2 | **6.1** |
| 20% | 34.2 | 10.3 | 3.4 | **0.0** | 110.2 | 39.8 | 9.2 | **6.1** |
| 30% | 44.5 | 20.5 | 6.8 | **3.4** | 131.7 | 113.3 | 9.2 | **6.1** |
| 50% | 47.9 | 41.1 | 6.8 | **3.4** | 202.1 | 196.0 | 9.2 | **9.2** |

NK.KKN: 0.292 station months, 14 candidate windows at the loosest margin. IO.EVN: 0.327
station months, 66 candidates. Exact Poisson intervals are in `results.json`; at these
counts the upper limits are several times the point values.

* **The spectral test alone cannot carry margin.** Loosening it by 20 percent doubles
  NK.KKN's rate and adds a quarter to IO.EVN's. By 50 percent IO.EVN triggers on most
  windows with a signal.
* **The H/V rule takes the margin well at NK.KKN and badly at IO.EVN.** At 20 percent
  it holds NK.KKN to 10 and IO.EVN to 40; at 30 percent IO.EVN's H/V threshold (1.39)
  falls into the bulk of its noise and the rule stops working.
* **The partner station is the rule that does not degrade.** Requiring the other
  station's trigger to fit a source in the basin box holds IO.EVN at 9.2 at every
  margin and NK.KKN at 0 to 6.8. Its cost is availability: the partner had no data for
  11 to 16 of IO.EVN's spectral windows, and those are outside the counts.
* **Together, at 20 percent margin: NK.KKN 0, IO.EVN 6.1.** Both are within a factor
  of ten of the target of 1 for the first time, and NK.KKN meets it on this corpus,
  though 0 in 0.29 station months only bounds the rate below 12.6.

Run 2026-09-26. The horizontals and partner waveforms for 80 candidate windows were
fetched and are now cached.

## What each margin means

At 20 percent the NK.KKN rule accepts LF/HF at or above 3.94 (the cascade gave 4.92),
a centroid at or below 2.26 Hz (1.89), and H/V at or above 1.86 (2.32). At IO.EVN it
accepts 12.06 (15.07), 1.84 Hz (1.53), and 1.58 (1.98). These are the values the live
loop should run with, and they are a choice, not a measurement: the true spread of real
events around the one known one is unknown, and 20 percent is a guess at it.

## The other cost: earthquakes that pass

Margin also lets more real earthquakes through the spectral test. Recomputed from the
cache for every earthquake in both corpora (`earthquake_overlap.py`):

| Margin | NK.KKN, of 64 | IO.EVN, of 132 |
|---:|---:|---:|
| 0 | 11 (17.2%) | 6 (4.5%) |
| 10% | 12 (18.8%) | 7 (5.3%) |
| 20% | 14 (21.9%) | 8 (6.1%) |
| 30% | 19 (29.7%) | 9 (6.8%) |
| 50% | 24 (37.5%) | 12 (9.1%) |

At 20 percent the earthquake overlap rises from 17.2 to 21.9 percent at NK.KKN and
from 4.5 to 6.1 percent at IO.EVN. Distant earthquakes are removed by the catalogue
check before this rule runs; the ones that pass here are regional, and for those the
H/V rule, the partner station, and the gauge are what stand between a regional
earthquake and a Warning.

## Decision

The defaults now carry the 20 percent margin: LF/HF at least 3.94, centroid at most
2.26 Hz, H/V at least 1.86 over the decision segment, with the H/V rule on. The
configuration comments say where each number comes from, and the classifier's reason
string carries the 21.9 percent earthquake overlap measured at this operating point.

## The basin box

The partner rule here asks whether the pair of arrival times fits a source inside
27.95 to 28.45 N, 85.20 to 85.70 E, a box drawn by hand around the upper Trishuli and
Bhote Koshi. It is wider than the 2026 zone of exp019 (which gave 3.1 at IO.EVN) and
narrower than the whole region (21.4). It should be replaced by the catchment outline
when river geometry is available; until then it is stated so it can be argued with.

## What this does not settle

* **Availability.** The partner and the horizontals are dependencies. In this corpus
  the horizontals were always available and the partner was missing for up to a quarter
  of IO.EVN's candidate windows. In operation the loop reports both, and a decision made
  without them is a single station decision at the single station rate.
* **The miss side.** Every rule was checked against the one positive event, which
  passes by construction. What margin a second real event would need is unknown.
* **Small counts.** The best cells hold 0 to 2 windows. The intervals say so.

## Design

exp018's basis and station months. For each candidate window the horizontals and the
other station's vertical were fetched once and every rule evaluated at every margin from
the same segments. Two station tests use `ghadi.associate` with the speed range 2.5 to
6.5 km/s and 5 s tolerance. The H/V value is over the 120 s decision segment.
