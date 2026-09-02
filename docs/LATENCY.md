# Real-time latency on NK.KKN (issue 0.1, blocker B4)

**Why this document exists.** Everything the handoff verified was *archive* retrieval.
Whether the same data arrives fast enough to act on was unmeasured, and it is the single
question that decides whether GHADI is a real-time warning system or a retrospective
analysis project. If latency exceeds roughly 120 s there is no room left in the 180 s
end-to-end budget and the project must be re-scoped honestly.

## Preliminary result — 2026-09-02

**The feed exists, it is reachable, and it is fast.**

| Quantity | Value |
|---|---|
| Server | `rtserve.iris.washington.edu:18000` (SeedLink) |
| Stream | `NK.KKN..BHZ`, 50 Hz |
| Sample | 41 packets over ~3.5 minutes |
| Median latency | **16.0 s** |
| Mean | 15.7 s |
| p90 | 18.2 s |
| p95 | **22.3 s** |
| p99 / max | 23.3 s |

Latency is measured as `now − packet_end_time`: the age of the newest sample in the
packet at the moment it reached us, which is the quantity the detection path actually
pays.

**Preliminary verdict: real-time operation is viable.** A p95 of 22 s leaves roughly
158 s of the 180 s end-to-end budget for detection, fusion, the human gate and
dissemination.

## This is not yet issue 0.1

Issue 0.1 asks for a **7-day** distribution, and this is three and a half minutes. What
a short sample cannot show:

- the tail — station dropouts, network partitions, server restarts;
- diurnal or weekly structure in the path from Nepal to the EarthScope ring buffer;
- behaviour during a monsoon telecom disruption, which is exactly when it matters;
- what happens during a real event, when the station may be shaken or the backhaul cut.

**A median is not a guarantee.** The operating question is not "how fast is it usually"
but "how often is it too slow, and for how long", and that needs the full run:

```bash
uv run python scripts/seedlink_latency.py --hours 168 --out latency_log.csv
uv run python scripts/seedlink_latency.py --report latency_log.csv
```

Record the resulting distribution here, replacing the preliminary table but keeping
this section, so the difference between a smoke test and a measurement stays visible.

## Implementation note

ObsPy's `create_client` connects immediately and the underlying `SeedLinkConnection`
defaults its timeout to `None`, so `connect()` raises
`TypeError: '<' not supported between instances of 'float' and 'NoneType'` before
reaching the network. The probe therefore builds the client with `autoconnect=False`,
sets `conn.timeout`, and connects explicitly.
