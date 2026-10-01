# Experiment 024: how low should the distant earthquake threshold go?

**Question.** The first live shadow run staged one Advisory in 20 hours. It was an M5.2
earthquake near Yemen, 36 degrees away, whose first waves reached Kakani at the moment
of the trigger. The suppressor considered only M5.5 and above (exp006), and the live
loop had no catalogue feed at all. Lowering the threshold catches more of these and
spends more time with the seismic channel set aside. What does each rule buy and cost?

**Answer.** About a third to a half of the false alarms that survive at IO.EVN are
earthquakes between M5.0 and M5.5. Admitting those only when they are within 80 degrees
explains 10 of 29 for about twice the set aside time, and explains the live case.

| Rule | Time set aside | IO.EVN false alarms explained | NK.KKN explained | Live case 26 Sep |
|---|---:|---:|---:|---|
| M5.5 anywhere (exp006) | 3.7% | 0 of 29 | 0 of 4 | no |
| M5.5 anywhere, M5.0 within 40 degrees | 4.2% | 3 | 0 | yes |
| M5.5 anywhere, M5.0 within 60 degrees | 6.2% | 7 | 1 | yes |
| **M5.5 anywhere, M5.0 within 80 degrees** | **7.2%** | **10** | **1** | **yes** |
| M5.5 anywhere, M5.0 within 100 degrees | 8.1% | 11 | 1 | yes |
| M5.0 anywhere | 13.8% | 15 | 2 | yes |

Period 2024-01 to 2026-07, 20,621 origins at M4.5 and above from the USGS catalogue,
cached in `catalogue_m45.json`. False alarms are exp018's.

* **These are not chance matches.** At 80 degrees the extra windows cover 3.5% of the
  time, so about 1 of 29 random moments would fall in one. Ten did.
* **The corpus was built with the M5.5 rule,** which is why that rule explains none of
  what is left. Everything explained here is new.
* **Set aside is not blind.** In a set aside window the seismic channel reports quiet
  and the gauge is untouched. Without a gauge, though, it is blind, and 7.2% of the time
  is about 1 hour 44 minutes a day spread over many short windows.
* **M5.0 anywhere buys five more for nearly twice the time.** It was judged not worth
  it. The choice is a judgement about a miss rate nobody can measure with one event.

Run 2026-10-01.

## The decision

The defaults are now M5.5 and above at any distance and M5.0 and above within 80
degrees (`SuppressionConfig`). The first live Advisory is explained under it: M5.2 at
36 degrees, detection inside its window.

## The catalogue is late, and the service now says so

The Yemen origin was at 16:33:43 UTC. Its waves tripped the detector at 16:40:26 and
the decision was made about two and a half minutes later. A global agency typically
publishes an M5 origin ten to twenty minutes after the earthquake. So even with the
feed, the live service would probably have staged this Advisory first and learned why
afterwards.

The shadow runner now does both. `ghadi.origins_feed.RollingOrigins` refreshes the
catalogue every two minutes and passes what is known to each decision. When a new
origin arrives that explains a decision already made, the runner records it, counts it,
and attaches the explanation to the staged alert, so the person at the outbox sees
"since explained" beside it. The alert stays staged: only a person closes it.

## What this does not show

* The share of real slope failures that would start inside a set aside window. With one
  event it cannot be measured; 7.2% is the prior.
* How late the catalogue is in practice. The live run will measure it: the time from a
  decision to its explanation is now recorded.
* Regional earthquakes, which the catalogue check does not cover. Those are the
  22 in 100 that the other rules must handle (exp022).
