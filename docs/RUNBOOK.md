# Running GHADI in shadow mode

This is for the person who keeps the service running for a monsoon. It assumes nothing
about the science. Shadow mode means the system decides, records the decision, and
sends nothing. Every alert it would have raised waits for a person.

## What runs

One process, one station, one river reach. It connects to a public SeedLink server,
builds 4 minute windows that start every minute, runs the detector on each, and writes
one line per decision to an audit log whose lines are chained by hash. It also writes a
status file after every window and answers a health check on a local port.

| Thing | Where |
|---|---|
| Settings | `deploy/ghadi.toml`, or the file you pass with `--settings` |
| State directory | `state_dir` in the settings; `data/shadow` by default |
| Audit log | `<state_dir>/audit.jsonl` |
| Status file | `<state_dir>/status.json` |
| Staged alerts | `<state_dir>/staged/` |
| Delivery log | `<state_dir>/delivery.jsonl` |
| Desk outbox | `<state_dir>/outbox/` |
| Health check | `http://127.0.0.1:8771/health` |

## Start

Without a container:

```bash
python scripts/run_shadow.py live --settings deploy/ghadi.toml --hours 0
```

With the container and systemd, see the comments in `deploy/ghadi-shadow.service`.

To try it for one hour on your own machine, leave out `--settings` and pass `--hours 1`.
State goes to `data/shadow`.

## Check it daily

1. Open the health check. `ok` must be true. If it is false the reply says why:
   the feed is stale, the audit chain is broken, or no window has arrived for ten
   minutes since start.
2. Look at `feed.delay_p95_s` in the same reply. Above 120 the feed is too slow to act
   on, and the project's own rule says it must be re-scoped, not worked around.
3. Look at `staged_waiting_for_a_person`. If it is above zero, a decision is waiting:

```bash
python scripts/outbox.py --settings deploy/ghadi.toml list
```

4. Once a week, check the chains:

```bash
python -c "from ghadi.service import verify_chain; print(verify_chain('data/shadow/audit.jsonl'))"
```

```bash
python scripts/outbox.py --settings deploy/ghadi.toml verify
```

## When a decision is waiting

Read it in full before doing anything:

```bash
python scripts/outbox.py --settings deploy/ghadi.toml show <staged id>
```

Approve it only if you are the person allowed to forward advisories under the operating
agreement, and put your name on it. Approval delivers to the desk outbox directory and,
if a webhook has been agreed with the receiving office, to that endpoint. Nothing else.

```bash
python scripts/outbox.py --settings deploy/ghadi.toml approve <staged id> --by "Your Name" --note "why"
```

If it should not go anywhere, reject it with your name and a reason. A rejection is on
the record too.

## What failure looks like

| You see | It means | Do |
|---|---|---|
| `ok: false`, `seconds_since_last_window` large | The feed stopped or the server dropped us | Nothing at first. The loop reconnects with a growing wait. If it stays down for an hour, check the server name in the settings and whether the machine has network |
| `reconnections` climbing every few minutes | The server keeps closing the connection | Report it. The public server may be rate limiting; do not add a second connection |
| `feed.unusable_windows` climbing | Packets arrive with gaps | The station side, not ours. Note it in the log; the detector refuses windows that are mostly gaps rather than deciding on them |
| `audit_chain_ok: false` | A line in the audit log was altered or lost | Stop the service. Keep the file. This is the one thing that must be looked into before restarting |
| The process exits | An error the loop could not recover from | systemd restarts it after 10 s. Read the last lines of the journal and report them |
| `feed.delay_p95_s` above 120 | The feed is too slow for warning | Report it. This is a finding about the feed, not a fault to fix here |

## Stop

```bash
sudo systemctl stop ghadi-shadow
```

Or Ctrl-C in a terminal. The loop finishes the window it is on, writes the status file,
and exits. Nothing is lost: windows still open when it stops are not decided on, and
the next start begins with the next whole window.

## What never happens in this mode

* No message leaves the machine without a named person approving it.
* No alert is ever marked as real or public. The message status stays `Test` and the
  scope stays `Restricted` in every build that is not the authorised one.
* No setting in the file can change either of those. The service refuses a settings
  file that tries.
