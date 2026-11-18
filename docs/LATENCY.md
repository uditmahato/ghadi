# Real-time latency on NK.KKN (issue 0.1, blocker B4)

**Why this document exists.** Everything the handoff verified was *archive* retrieval.
Whether the same data arrives fast enough to act on was unmeasured, and it is the single
question that decides whether GHADI is a real-time warning system or a retrospective
analysis project. If latency exceeds roughly 120 s there is no room left in the 180 s
end-to-end budget and the project must be re-scoped honestly.

## Result, 2026-11-02 to 2026-11-18: 15.8 days on the live shadow service

**The seven day run issue #8 asks for is done, at more than twice that length. The feed
is fast and steady enough for warning: no break longer than 120 s in 15.8 days.**

| Quantity | Value |
|---|---|
| Server | `rtserve.earthscope.org:18000` (SeedLink) |
| Stream | `NK.KKN..BHZ`, `BHN`, `BHE`, 50 Hz |
| Period | 2026-11-02 08:14 to 2026-11-18 03:46 UTC, 15.8 days |
| Windows decided | 22,773, one a minute, each 4 minutes long |
| Windows with usable data | 22,738 |
| **Hours watched** | **378.97** of about 379.5 (99.8 percent) |
| Service starts | 2, both on the record |
| Windows that arrived late (stale) | 9 |
| Median window delay | **22.48 s** |
| 95th percentile | **25.98 s** |
| 99th percentile | 27.35 s |
| Maximum | 168.63 s |
| **Interruptions > 120 s** | **0** |

Read on the machine with:

```bash
sudo docker exec ghadi-shadow python scripts/feed_report.py --settings /etc/ghadi/ghadi.toml --since 2026-11-02T08:14Z
```

**The window delay is not the same number as the packet delay below.** Each window
records the delay of the latest packet in it, so the window figure is the worst packet
of each minute, not a typical packet. That is why its median (22.5 s) sits above the
3.4 hour run's packet median (15.8 s) while its 95th percentile (26.0 s) is close to that
run's packet maximum (27.1 s). The window delay is the one the decision pays, because a
window cannot be decided until its last packet has arrived.

**What it means for warning.** In 99 windows of 100 the data was at most 27.4 s old when
it was decided on. The one 169 s case is a single window. exp020's 156 s from trigger
onset to decision already includes a feed delay of this size, so the 160 s warning
latency in the configuration stands.

**What this run still does not cover.** The monsoon, when telecom links fail and when
warning matters most, and a real event, when the station may be shaken or its link cut.
The run continues to the end of the 2027 monsoon to measure both (see
[LIVE_RUN.md](LIVE_RUN.md)).

## Earlier result, 2026-09-02: 3.4 hours continuous

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

The server name in the table was right on the day it was measured. EarthScope has since
moved the server to `rtserve.earthscope.org:18000`, and the old name no longer resolves
(found 2026-10-30). NK.KKN streams BHZ, BHN and BHE there. The scripts and the service now
use the new name.

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

## Why the 3.4 hour run was not enough

The 15.8 day run above now answers the first three points below. The section is kept so
the difference between a partial run and the measurement stays visible.

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

To run the full measurement (against `rtserve.earthscope.org:18000`, the default):

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

## Update, 2026-09-25

The log now holds 3,596 packets over about 7 hours across 2 and 3 September 2026. The
distribution did not move: median 15.7 s, p95 22.8 s, maximum 27.1 s. This is still far
short of the seven day run issue #8 asks for. The shadow service (`scripts/run_shadow.py
live`) now measures the same quantity for every window it decides on, so a seven day
shadow run is the seven day latency run.

Until 2026-11-02 those per window delays were kept only in memory, so every restart
started the figures again. The service now writes every window to `windows.jsonl` in its
state directory, across restarts, and this prints the distribution over any period:

```bash
python scripts/feed_report.py --settings deploy/ghadi.toml --since 2026-11-02T00:00Z
```

It reports the delay percentiles from windows that arrived on time, the number of
interruptions longer than 120 s and the longest one, how many times the service
started, and the hours watched, which is what a false alarm rate is divided by.

exp020 measured a different and larger number: the time from a trigger onset to a
decision on the live path, about 156 s in the median and up to 186 s. That is the
decision segment (120 s), the feed delay, and the wait for the window that holds the
whole segment to close. The 60 s warning latency in the configuration predates the live
path and understates it.
