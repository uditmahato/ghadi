# Running the shadow service on AWS

The shadow service has to run day and night for months. A laptop sleeps, so it stops
(the first live run did, on 1 October 2026). This guide puts it on one small machine in
AWS. It takes about fifteen minutes, most of it waiting.

The service only reads a public data feed and writes to its own disk. It needs no
password, no key and no open port apart from the one you use to log in. It stays in
shadow mode: nothing is sent to anyone.

## What you need

* An AWS account, with a card on file. Only you can create it.
* About 5 to 10 US dollars a month. Check the current prices on the AWS site before you
  launch: they change, and new accounts sometimes get a free year on the smallest
  machine.

## Pick a machine

| Choice | Why |
|---|---|
| **Lightsail**, the 1 GB plan, or **EC2** `t3.micro` | Enough for one process. Lightsail has one flat monthly price and is simpler; EC2 gives more control |
| **Ubuntu 24.04** | The first boot script is written for it |
| **x86**, not ARM (Graviton) | The seismology library installs without trouble on x86 |
| **Region: Mumbai** (`ap-south-1`) | Closest to Nepal and to the people who would use it later. Any region works: the feed comes through a server in the United States, so the region adds less than a second |
| **Disk: 20 GB** | The state grows by a few megabytes a month |

## Launch it

### On Lightsail

1. Open Lightsail, choose **Create instance**, pick the Mumbai region.
2. Platform **Linux/Unix**, blueprint **OS Only**, **Ubuntu 24.04 LTS**.
3. Choose **Add launch script** and paste the whole of
   [`deploy/aws-user-data.sh`](../deploy/aws-user-data.sh).
4. Pick the 1 GB plan, give it the name `ghadi-shadow`, and create it.
5. In the instance's **Networking** tab, delete every firewall rule except SSH.

### On EC2

1. Open EC2 in the Mumbai region and choose **Launch instance**.
2. Name `ghadi-shadow`, image **Ubuntu Server 24.04 LTS (x86)**, type `t3.micro`.
3. Create or choose a key pair, so you can log in.
4. Network settings: allow SSH from **My IP** only. Allow nothing else.
5. Storage: 20 GB, `gp3`.
6. Under **Advanced details**, paste the whole of
   [`deploy/aws-user-data.sh`](../deploy/aws-user-data.sh) into **User data**.
7. Launch.

## Check that it started

Wait about ten minutes: the first boot installs Docker and builds the image. Then log
in (the **Connect** button in the AWS console opens a terminal in the browser) and run:

```bash
tail -n 5 /var/log/ghadi-setup.log
```

The last lines should say `ghadi setup finished`. Then:

```bash
curl -s http://127.0.0.1:8771/health
```

`ok` should be true within a few minutes of the start. If it is not, the reply says why;
the table in [RUNBOOK.md](RUNBOOK.md) explains each case. The service's own log:

```bash
sudo journalctl -u ghadi-shadow -n 50
```

## Day to day

Everything in [RUNBOOK.md](RUNBOOK.md) applies. The only difference is that the
commands run inside the container, so put `sudo docker exec ghadi-shadow` in front:

```bash
sudo docker exec ghadi-shadow python scripts/outbox.py --settings /etc/ghadi/ghadi.toml list
```

```bash
sudo docker exec ghadi-shadow python scripts/outbox.py --settings /etc/ghadi/ghadi.toml verify
```

The audit log, the status file and the outbox are on the machine in `/var/lib/ghadi`.

## Update to a newer version

After a change is merged into `main`, log in and run the first boot script again. It
fetches the new code, rebuilds, and keeps your settings and your state:

```bash
sudo bash -c "curl -fsSL https://raw.githubusercontent.com/uditmahato/ghadi/main/deploy/aws-user-data.sh | bash"
```

```bash
sudo systemctl restart ghadi-shadow
```

## Keep a copy of the record

The audit log is the evidence the paper will rest on. Copy `/var/lib/ghadi` off the
machine once a week, for example:

```bash
scp -r ubuntu@<machine address>:/var/lib/ghadi ./ghadi-state-backup
```

For a hands off copy, turn on automatic snapshots of the disk in the console (Lightsail:
the instance's **Snapshots** tab; EC2: a Data Lifecycle Manager policy). Snapshots cost a
little extra.

## Stop paying

Stopping the service is `sudo systemctl stop ghadi-shadow`. To stop the bill, copy the
state off first, then delete the instance in the console. A stopped EC2 machine still
pays for its disk.

## What this setup deliberately does not do

* It opens no port for the health check or the status page. Read them from the machine,
  or through an SSH tunnel: `ssh -L 8771:127.0.0.1:8771 ubuntu@<machine address>`.
* It holds no credentials. If a webhook to a receiving office is ever agreed, its
  address is given to `outbox.py --webhook` by the person approving, never
  written into the repository.
* It runs one station connection. Do not start a second copy against the same public
  server.
