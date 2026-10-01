# Experiment 027: what does each rule add? One table, one basis.

**Question.** The rules were measured one at a time on slightly different bases. On the
same noise corpora at the operating point the system runs at, what does each rule add,
alone and together, and what is lost when one is taken away?

**Answer.** The partner station does most of the work. The catalogue and the H/V rule
each help on their own, and add nothing once the partner is in. The honest operating
number has to count the times the partner is missing: about 3 false alarms per station
month at NK.KKN and 15 at IO.EVN.

False alarms per station month, defaults (20 percent margin). Windows in brackets.

| Rules | NK.KKN | IO.EVN |
|---|---:|---:|
| Trigger only | 369.9 (108) | 1137.6 (372) |
| + spectral | 34.3 (10) | 110.1 (36) |
| + catalogue | 24.0 (7) | 82.6 (27) |
| + H/V | 6.9 (2) | 36.7 (12) |
| + partner in the catchment | **0.0** (0) | **6.1** (2) |
| All rules, falling back to catalogue and H/V when the partner has no data | **3.4** (1) | **15.3** (5) |

One rule added to the spectral test, and one rule left out of the full set:

| | NK.KKN added | NK.KKN left out | IO.EVN added | IO.EVN left out |
|---|---:|---:|---:|---:|
| Catalogue | 24.0 | 0.0 | 82.6 | 6.1 |
| H/V | 10.3 | 6.9 | 39.8 | 6.1 |
| Partner | 6.9 | 6.9 | 9.2 | 36.7 |

NK.KKN: 0.292 station months, 366 windows. IO.EVN: 0.327 station months, 409 windows.
Run 2026-10-01, fully offline from the results of exp018, exp022, and exp024. Exact
Poisson intervals are in `results.json`; with counts this small the upper limits are
three to five times the point values.

* **The spectral test removes nine tenths of the triggers** and still leaves 34 and
  110 a month. It is necessary and nowhere near sufficient.
* **The partner rule is the strongest single addition:** 34 to 6.9 at NK.KKN and 110
  to 9.2 at IO.EVN on its own. Leaving it out of the full set costs the most at IO.EVN.
* **The catalogue is redundant with the partner rule on this corpus, and H/V nearly so.**
  Leaving the catalogue out of the full set changes nothing. Leaving H/V out changes
  nothing at IO.EVN and costs 6.9 at NK.KKN. They are not redundant with each other:
  together without the partner they give 6.9 and 36.7.
* **They are what stands when the partner is down.** The partner had no data for 3 of
  NK.KKN's 10 spectral windows and 11 of IO.EVN's 36. A window that cannot be
  corroborated falls back to the catalogue and H/V rules, and with that fallback the
  rates are 3.4 and 15.3. Those are the numbers to quote for the system as it would
  run, not 0 and 6.1.
* **A distant earthquake passes the partner rule,** because both stations see it
  (exp025). The catalogue is what removes those, so it is not optional even where this
  table shows it adding nothing.

## What this does not show

* The miss side. Each rule also has a cost in events not detected, which exp026
  estimates by injection.
* Independence between corpora. Both stations' windows come from the same 30 months.
* A calibrated rate. Five windows in a third of a station month is a wide interval.

## Design

A window is a false alarm under a set of rules if any of its trigger segments passes
every rule in the set. Spectral, H/V, and partner values per segment are exp022's. The
partner rule uses the catchment above Bidur derived from an elevation model
(`data/geo`), which replaced a hand drawn box on 2026-10-01 and moved two NK.KKN cells.
The catalogue rule uses exp024's M4.5 catalogue and the default suppression rule (M5.5
anywhere, M5.0 within 80 degrees). The trigger only row is exp018's.
