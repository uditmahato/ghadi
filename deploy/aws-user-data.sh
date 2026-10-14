#!/bin/bash
# GHADI shadow service: first boot script for a fresh Ubuntu 24.04 machine.
#
# Paste this file into "User data" when you launch the machine (EC2 or Lightsail). It
# runs once, as root, on first boot. It installs Docker, fetches the code, builds the
# image, and starts the service under systemd. The progress is in
# /var/log/ghadi-setup.log. See docs/DEPLOY_AWS.md for the whole procedure.
#
# Nothing here needs a password, key or token: the repository is public and the station
# feed is public. Nothing is sent anywhere; the service stays in shadow mode.

set -euo pipefail
exec > >(tee -a /var/log/ghadi-setup.log) 2>&1

REPO_URL="https://github.com/uditmahato/ghadi.git"
BRANCH="main"
SRC=/opt/ghadi-src

echo "ghadi setup started $(date -u +%FT%TZ)"

# A small machine has 1 GB of memory. Swap keeps the image build from running out.
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends docker.io git curl ca-certificates
systemctl enable --now docker

# Keep the clock right: every decision is stamped with it.
timedatectl set-ntp true || true

if [ -d "$SRC/.git" ]; then
    git -C "$SRC" fetch --depth 1 origin "$BRANCH"
    git -C "$SRC" checkout -B "$BRANCH" FETCH_HEAD
else
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$SRC"
fi

docker build -t ghadi:latest "$SRC"

mkdir -p /etc/ghadi /var/lib/ghadi
# Keep a settings file that was already edited on this machine.
[ -f /etc/ghadi/ghadi.toml ] || cp "$SRC/deploy/ghadi.toml" /etc/ghadi/ghadi.toml
chown 10001:10001 /var/lib/ghadi

cp "$SRC/deploy/ghadi-shadow.service" /etc/systemd/system/ghadi-shadow.service
systemctl daemon-reload
systemctl enable --now ghadi-shadow

echo "ghadi setup finished $(date -u +%FT%TZ)"
echo "check it with: curl -s http://127.0.0.1:8771/health"
