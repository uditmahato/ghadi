# The live shadow run: what is being collected, where, for how long, and why

Since 30 October 2026 the shadow service has run day and night on a live seismic feed.
It decides on every minute of data and writes what it saw to disk. It sends nothing to
anyone: every alert it would have raised waits for a named person, who approves or
rejects it on the record. This page says what that run collects and what each piece is
for. Every time on this page is UTC.

## Where it runs

| What | Value |
|---|---|
| Machine | One small AWS Lightsail instance (1 GB plan, Ubuntu 24.04) in the Sydney region. Set up by [DEPLOY_AWS.md](DEPLOY_AWS.md) |
| Process | `scripts/run_shadow.py live` in a Docker container, kept running by the systemd unit `ghadi-shadow` |
| Settings | `/etc/ghadi/ghadi.toml` on the machine, copied from [`deploy/ghadi.toml`](../deploy/ghadi.toml) |
| Records | `/var/lib/ghadi` on the machine |
| Tier | T0, shadow. Nothing leaves the machine |
| Run by | Udit Kumar Mahato |

The region does not matter for the measurement: the feed comes from a server in the
United States, and the delay is measured from the station, not from the machine.

## Where the data comes from

| Source | What the service takes from it | How often |
|---|---|---|
| EarthScope SeedLink, `rtserve.earthscope.org:18000` | The live ground motion from the Kakani broadband station `NK.KKN`, all three directions (BHZ, BHN, BHE) at 50 samples a second. This is the only input the detector decides on | Continuously, a packet every few seconds |
| USGS earthquake catalogue, `earthquake.usgs.gov/fdsnws/event/1/query` | Every earthquake the USGS publishes worldwide, so a distant earthquake can be set aside, or explained after the fact when it is published late | Every two minutes |

Not collected yet, and why:

* **A second station.** The partner `IO.EVN` near Everest has no live public feed (see
  [DATA_SOURCES.md](DATA_SOURCES.md)), so the run has no partner for now.
* **River gauges.** The DHM gauge data needs an agreement that is not in place.
* **The raw waveforms.** The service reads each packet, decides and lets the samples go.
  EarthScope keeps an archive of NK.KKN, but it has gaps of months. Keeping the raw
  data would cost about 10 to 15 MB a day and is an open decision.

## What is written to disk

All of it is in `/var/lib/ghadi` on the machine. Copy that directory off once a week.

| File | What one line holds | When it grows | What it is for |
|---|---|---|---|
| `windows.jsonl` | Every 4 minute window, one a minute, quiet ones too: its time, what the detector said, how much of it had data, and how late the data arrived. Also one line each time the service starts or stops | Once a minute, about 350 kB a day. Started 2026-11-02 08:14 | The latency run, and the hours watched, which every false alarm rate is divided by |
| `audit.jsonl` | Every window where the detector triggered: the onset time, the signal measures, whether a known earthquake explains it, the alert tier and why. Each line is chained to the one before by a hash, so a changed or lost line shows | Only on a trigger, a few times a day | The false alarms themselves, and evidence that the record was not edited |
| `delivery.jsonl` and `staged/` | Every alert the service would have raised, every "explained later" note, and every approval or rejection with a person's name | Only when an alert clears a tier | How often a person would have been asked to act, and what they decided |
| `status.json` | A snapshot of the feed health and the last decisions | Rewritten every 30 s, does not grow | The daily check |

## How long it runs, and what each stage gives

Run it without stopping until the end of the 2027 monsoon. Each stage gives a result on
its own, so nothing waits a year.

| Run length | Date reached | What it answers | Where the result goes |
|---|---|---|---|
| **7 days** | 2026-11-09, after 08:14 | Is the feed fast and steady enough for warning? The full week of feed delays and outages, which issue #8 asks for. Until now only 7 hours were measured | [LATENCY.md](LATENCY.md) |
| **1 month** | about 2026-12-02 | The first false alarm rate measured live for a whole station month. The current figures rest on about a third of a station month | [RESEARCH_REPORT.md](RESEARCH_REPORT.md), the paper |
| **6 months** | about 2027-05-02 | The handoff's minimum viable result: a false alarm rate on at least six months of continuous NK.KKN data, across the dry season and the winter | The paper |
| **One full monsoon** | about October 2027 | The project's own rule: no step past shadow mode, not even advisories to officials, without at least one full monsoon in shadow. The monsoon is when floods happen and the ground is noisiest | The case for tier T1 |

Time the service was down is time the system saw nothing. Each start and stop is on the
record, so outages are counted, not hidden.

## How the data will be used

* **Latency.** The delay of every window, from the station to the machine, gives the
  distribution the warning time is built on. If the delay often passed 120 s, there
  would be no time left to warn anyone, and the project would have to be re-scoped.
  In the first 19 minutes of the window log it was about 23 s in the median and 25.5 s
  at the 95th percentile.
* **False alarm rate.** Triggers that turn into an alert, divided by the hours the
  system was really watching, give alarms per station month. The goal is 1. Until now it
  was measured only on archived data.
* **The distant earthquake check, on live data.** Each alert that a later published
  earthquake explains shows how often the catalogue arrives too late. The first one was
  an M6.0 earthquake under Japan on 2026-10-31.
* **The human step.** Each approval or rejection, with a name and a reason, shows how
  the outbox works in practice before anyone outside the project relies on it.
* **A real event, if one happens.** If a slope fails upstream during the run, the
  decision, its timing and the reasoning are on the record as they happened, not
  rebuilt afterwards. That would be the second confirmed event the project needs.

None of this is a public warning. The run measures whether a warning would be possible
and how often it would be wrong.

## Checking it

The daily check and what each failure means are in [RUNBOOK.md](RUNBOOK.md). The figures
over any period, across restarts:

```bash
sudo docker exec ghadi-shadow python scripts/feed_report.py --settings /etc/ghadi/ghadi.toml --since 2026-11-02T00:00Z
```

Anything waiting for a person:

```bash
sudo docker exec ghadi-shadow python scripts/outbox.py --settings /etc/ghadi/ghadi.toml list
```

## Log of the run

| Date | What happened |
|---|---|
| 2026-10-30 | Service started on the machine. The old server name `rtserve.iris.washington.edu` no longer existed, so it was moved to `rtserve.earthscope.org` |
| 2026-10-31 | One alert staged: an M6.0 earthquake 352 km deep under Japan, published after the decision. Later rejected on the record by Udit Kumar Mahato |
| By 2026-11-02 | Clean stop on restart, a guard against placeholder names in the outbox, and the window log added. The window log starts at 08:14, so the seven day count starts there |
