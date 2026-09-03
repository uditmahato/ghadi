# Real-time latency on NK.KKN (issue 0.1, blocker B4)

**Why this document exists.** Everything the handoff verified was *archive* retrieval.
Whether the same data arrives fast enough to act on was unmeasured, and it is the single
question that decides whether GHADI is a real-time warning system or a retrospective
analysis project. If latency exceeds roughly 120 s there is no room left in the 180 s
end-to-end budget and the project must be re-scoped honestly.

## Result — 2026-09-02, 3.4 hours continuous

**The feed exists, it is reachable, it is fast, and over this window it did not drop.**

| Quantity | Value |
|---|---|
| Server | `rtserve.iris.washington.edu:18000` (SeedLink) |
| Stream | `NK.KKN..BHZ`, 50 Hz |
| Sample | **1,853 packets over 3.40 hours** (11:00–14:25 UTC) |
| Packet rate | 544 / hour |
| Median latency | **15.8 s** |
| Mean | 15.9 s |
| p90 | 21.6 s |
| p95 | **22.8 s** |
| p99 | 25.0 s |
| Maximum | **27.1 s** |
| **Interruptions > 120 s** | **0** |
| Largest inter-packet gap | 22.1 s (normal packet cadence, not an outage) |

Latency is measured as `now - packet_end_time`: the age of the newest sample in the
packet when it reached us, which is the quantity the detection path actually pays.

Stability across the window, which is the part a short sample cannot show:

| Hour (UTC) | Packets | Median | Max |
|---|---:|---:|---:|
| 11Z | 663 | 15.7 s | 26.0 s |
| 12Z | 581 | 15.8 s | 25.6 s |
| 13Z | 444 | 15.9 s | 27.1 s |
| 14Z | 165 | 15.5 s | 24.8 s |

**Verdict: real-time operation is viable on this feed.** A p95 of 22.8 s and a worst
observed case of 27.1 s leave roughly 153 s of the 180 s end-to-end budget for
detection, fusion, the human gate and dissemination.

An earlier 3.5-minute smoke test gave median 16.0 s and p95 22.3 s. The 3.4-hour run
reproduces that almost exactly (15.8 / 22.8), which is reassuring about the short
sample but does not extend its reach — see below.

## This still is not issue 0.1

Issue 0.1 asks for a **7-day** distribution. This is 3.4 hours, ended when the
collecting process was killed (exit code 4, no error output — the run did not crash on
its own). What 3.4 hours still cannot show:

- **Diurnal structure.** The window covers only 11Z–14Z, roughly 17:00–20:00 NPT. The
  quiet overnight hours and the busy morning are unmeasured.
- **Weekly structure**, and any maintenance window.
- **The tail that matters.** Zero interruptions in 3.4 hours bounds the outage rate
  only weakly: it is consistent with anything up to roughly one interruption per hour
  at 95% confidence. The operating question is not how fast the feed usually is but
  **how often it is too slow, and for how long**, and only a long run answers that.
- **Behaviour during monsoon telecom disruption**, which is exactly when it matters,
  and during a real event when the station may be shaken or the backhaul cut.

Note also that the archive coverage map (`data/corpus/availability.json`) shows
multi-month gaps in this station's *archive*. Whether those correspond to real-time
outages is unknown and worth asking NEMRC directly (blocker B3): a five-month archive
gap and a healthy real-time feed are not contradictory, but the combination needs
explaining before either is relied on.

To run the full measurement:

```bash
uv run python scripts/seedlink_latency.py --hours 168 --out latency_log.csv
uv run python scripts/seedlink_latency.py --report latency_log.csv
```

Record the resulting distribution here, replacing the table above but keeping this
section, so the difference between a partial run and the measurement stays visible.

## Implementation note

ObsPy's `create_client` connects immediately and the underlying `SeedLinkConnection`
defaults its timeout to `None`, so `connect()` raises
`TypeError: '<' not supported between instances of 'float' and 'NoneType'` before
reaching the network. The probe therefore builds the client with `autoconnect=False`,
sets `conn.timeout`, and connects explicitly.

The probe flushes every row to disk as it arrives, which is why 3.4 hours of data
survived the process being killed. Keep that property: a long collection that loses its
data on an unclean exit is worse than no collection, because it costs the same time and
yields nothing.
