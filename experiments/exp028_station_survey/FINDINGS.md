# Experiment 028: is there a third station?

**Question.** Two stations carry everything, and on 2026-10-01 one of them sent no live
data. Which open broadband stations lie within 300 km of the 2026 source, which hold
archive data for the event, which show it, and which are delivering live data now?

**Answer.** There is no third station. Of 33 broadband stations in the open catalogue
within 300 km, 31 belonged to a temporary network that closed in 2016. The two that
remain are the two already in use, and at the time of the probe neither was delivering
live data.

| | Count |
|---|---:|
| Broadband stations within 300 km in the open catalogue | 33 |
| Of those, temporary network XQ, operating 2015 to 2016 | 31 |
| Open on 26 August 2026 | 2 (NK.KKN, IO.EVN) |
| With archive data for the event | 2 |
| Showing the event | 2 |
| Delivering live packets in a 30 s probe on 2026-10-01 | 0 |

Run 2026-10-01 against the EarthScope station service, the archive, and the public
SeedLink server. The inventory is cached in `inventory.json`.

* **The system has exactly the two stations it has.** NK.KKN at 56 km and IO.EVN at
  131 km are the only open broadband stations within 300 km that were operating in
  2026. Every design choice that needs a second station needs one of these two.
* **Neither was live at the probe.** NK.KKN had been silent since at least 05:30 UTC
  that day (the shadow service counted 17 silent connections in an hour). IO.EVN sent
  nothing in 30 s either, though it does reach the archive, so it may be delivered by
  a different route or with a long delay. The server itself was up: two stations
  elsewhere in the world delivered packets in the same minutes. A live system on this
  feed has no partner station at all unless IO.EVN can be had in real time.
* **The temporary network is an opportunity for the past, not the present.** XQ put 31
  broadband stations across central Nepal from mid 2015 to 2016, the closest 14 km
  from the 2026 source. No catalogued mass movement falls in that period. But a year
  of dense data in the right place is the best available ground for measuring how a
  station's false alarm rate and the two station rule depend on spacing, and for
  hunting uncatalogued slope failures in the months after the Gorkha earthquake, when
  there were many.

## What this means

* **More stations are not available from open data.** The route to a third station is
  an agreement with the national network (issue #27's sibling, the DMG and NEMRC
  letter in `docs/outreach`), not a better search.
* **IO.EVN's live availability is now the first thing to settle.** The two station rule
  is the strongest rule the system has (exp027), and it needs IO.EVN in real time.
* **A positive class beyond one may be findable in 2015 to 2016.** That is a new
  experiment on the XQ archive.

## Limits

* The inventory is what one data centre lists as open. Stations of the national
  network that are not shared do not appear, and restricted channels were not probed.
* A 30 s live probe says what was true in those 30 s.
