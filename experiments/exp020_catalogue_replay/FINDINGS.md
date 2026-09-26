# Experiment 020: what would the system have said, and when, for each catalogue event? (#33)

**Question.** Milestone M5. For every catalogue event, push the archive waveform through
the real time path as a feed would have delivered it and record what the system would
have produced, using only data available at each moment.

**Answer.** For the 2026 event, an Advisory from each station about two and a half
minutes after the slope failed, with no gauge to lift it to a Warning. For every older
event, nothing that looks like a mass movement, on either station, anywhere in the
search window.

| Event | Time source | Search window | NK.KKN | IO.EVN |
|---|---|---|---|---|
| Jure 2014 | news | 45 min each side | before the archive | 4 decisions, none mass movement like |
| Langtang 2015 | news | 20 min each side | before the archive | 6 decisions, none |
| Melamchi 2021 | news | 3 h 15 min each side | 10 decisions, none | 42 decisions, none |
| Thame 2024 | news | 1 h 45 min each side | 2 decisions, none | 12 decisions, none |
| Rasuwagadhi 2025 | news | 1 h 15 min each side | 3 decisions, none | 11 decisions, none |
| **Bhote Koshi 2026** | seismic | 15 min each side | **Advisory at 02:52:30 UTC**, decided 02:55:00 | **Advisory at 02:52:43 UTC**, decided 02:55:00 |

Run 2026-09-25. Feed delay 6 s per packet, the measured median. No gauge for any event.

## The 2026 event, minute by minute

* **02:52:10** the slope fails (catalogued origin).
* **02:52:30** NK.KKN's trigger onset, 56 km away. **02:52:43** IO.EVN's, 131 km away.
* **02:55:00** the first window that holds a full 120 s decision segment after the
  onset closes at both stations, and each decides: mass movement like, Advisory, score
  0.60, held below Warning for want of a second source.
* Lead time at the default 60 s warning latency: Timure 3 min, Syabrubesi 10 min,
  Bidur 37 min. **At the latency this replay actually measured, about 156 s from onset
  to decision, Timure has about 1.4 min, Syabrubesi 8.4, Bidur 35.4.**

The decision latency is not a bug to be tuned away. The decision segment is 120 s long
by design (exp005), the feed adds 6 s, and the window that holds the segment closes up
to a minute after it ends. The floor is about 126 s and the replay's median is 156 s.
The 60 s budget in the configuration was written before the live path existed, and it
is wrong. Every lead time quoted so far from that budget is about 1.6 minutes too
generous.

## A threshold with no margin

The IO.EVN operating point is the cascade's own segment values from exp010, quoted to
four decimals. With those rounded values the live path **missed** the 2026 event at
IO.EVN: its centroid came out at 1.53252 Hz against a limit of 1.5325. With the exact
values it is detected, on the same window. A threshold set at the one positive event's
own value has zero margin, and any difference in how the window is cut moves the event
across it. This was known in principle; the replay shows it happening.

## Older events

None of the five older events produces a mass movement like segment on either station,
in windows that cover their whole reported uncertainty. This matches exp008, which
found no cross station candidate for them, and exp016, which could not confirm Thame
from orbit. The reasons differ by event and none is the detector working as intended:

* Jure 2014 and Langtang 2015 predate the NK.KKN archive, so only IO.EVN, 94 and
  130 km away, could see them.
* Melamchi 2021 was a debris flow that built over hours; IO.EVN triggered 42 times in
  the 6.5 hour window and none of the segments had the cascade's low frequency shape.
* Thame 2024 was a lake outburst, mostly water. The seismic signature of water moving
  down a channel is not the signature this detector was built on.
* The thresholds are fitted to the 2026 event. A detector that fires only on things
  that look like 2026 will not fire on things that do not.

So the positive class is still one, the miss rate on the other kinds of event is
unmeasured, and this replay does not change either. What it does show is that the
detector did not fire on the *noise* around those events either: 104 decisions across
the older events, all correctly not mass movement like.

## Design

`ghadi.live` on packets cut from the archive, each station at its own operating point,
overlapping 240 s windows every 60 s, the same detector, segment, classifier, teleseism
check, and fusion as the shadow service. A window only decides when the whole decision
segment is inside it, so the features are computed on the same basis every threshold
was set on. Repeat sightings of one onset in later windows are marked as already
decided. The search window is the catalogued origin plus and minus its uncertainty and
15 minutes, as exp008 used.

## What this means

* **Correct the warning latency.** The configured 60 s should become about 160 s, and
  the README's lead times should be quoted from that.
* **Set thresholds with margin,** and say what the margin costs in false alarms, before
  anyone runs this live.
* **The gauge decides the tier.** Without it the best the system can say about 2026 is
  Advisory. That is the agreement in issue #27.
