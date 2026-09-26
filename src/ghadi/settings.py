"""Site settings from a file, so a deployment is not a code edit (issue #34).

``GhadiConfig`` holds the science: thresholds, operating points, budgets. This module
holds the things that differ between one machine running the service and another:
which station, which server, where the audit log goes, which port answers health
checks. They are read from a small TOML file and validated before anything starts.

Nothing here can loosen a safety rule. There is no setting for alert status, scope,
or delivery to the public, because those are decided by an authorised build and a
human approval, not by a file.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import STATION_SITES

__all__ = ["DEFAULT_SETTINGS_TOML", "SiteSettings", "load_settings"]

DEFAULT_SETTINGS_TOML = """\
# GHADI site settings. Everything a deployment needs that is not science.

[station]
key = "NK.KKN"                     # one of the stations in ghadi.config.STATION_SITES
server = "rtserve.iris.washington.edu:18000"
horizontals = true                 # also stream the N and E components (issue #37)
partner = "IO.EVN"                 # a second station whose triggers corroborate (#31), or ""

[reach]
id = "TRISHULI-R07"

[paths]
state_dir = "data/shadow"           # audit log, status file, delivery log, staged alerts

[health]
port = 8771                         # 0 disables the health endpoint

[feed]
window_s = 240.0
hop_s = 60.0
max_gap_fraction = 0.40
stale_feed_s = 120.0
"""


@dataclass(frozen=True)
class SiteSettings:
    station_key: str
    server: str
    reach: str
    state_dir: Path
    health_port: int
    window_s: float = 240.0
    hop_s: float = 60.0
    max_gap_fraction: float = 0.40
    stale_feed_s: float = 120.0
    horizontals: bool = True
    partner_key: str | None = None
    source_path: Path | None = field(default=None, compare=False)

    @property
    def audit_path(self) -> Path:
        return self.state_dir / "audit.jsonl"

    @property
    def status_path(self) -> Path:
        return self.state_dir / "status.json"

    @property
    def delivery_log_path(self) -> Path:
        return self.state_dir / "delivery.jsonl"

    @property
    def staging_dir(self) -> Path:
        return self.state_dir / "staged"

    @property
    def outbox_dir(self) -> Path:
        return self.state_dir / "outbox"


def _get(table: dict[str, Any], key: str, default: Any) -> Any:
    return table.get(key, default) if isinstance(table, dict) else default


def parse_settings(text: str, *, source: Path | None = None) -> SiteSettings:
    raw = tomllib.loads(text)
    station = raw.get("station", {})
    key = str(_get(station, "key", "NK.KKN"))
    if key not in STATION_SITES:
        raise ValueError(f"unknown station {key!r}; known: {sorted(STATION_SITES)}")
    partner = str(_get(station, "partner", "")).strip() or None
    if partner is not None and partner not in STATION_SITES:
        raise ValueError(f"unknown partner station {partner!r}; known: {sorted(STATION_SITES)}")
    if partner == key:
        raise ValueError("the partner station must be a different station")
    feed = raw.get("feed", {})
    window_s = float(_get(feed, "window_s", 240.0))
    hop_s = float(_get(feed, "hop_s", 60.0))
    if hop_s <= 0 or hop_s > window_s:
        raise ValueError("feed.hop_s must be positive and no longer than feed.window_s")
    gap = float(_get(feed, "max_gap_fraction", 0.40))
    if not 0.0 <= gap <= 1.0:
        raise ValueError("feed.max_gap_fraction must be between 0 and 1")
    port = int(_get(raw.get("health", {}), "port", 8771))
    if not 0 <= port <= 65535:
        raise ValueError("health.port must be a port number, or 0 to disable")
    for banned in ("alert", "cap", "delivery", "public"):
        if banned in raw:
            raise ValueError(
                f"settings may not contain a [{banned}] table: alert status, scope, and "
                "delivery are not configurable here"
            )
    state_dir = Path(str(_get(raw.get("paths", {}), "state_dir", "data/shadow")))
    if source is not None and not state_dir.is_absolute():
        state_dir = (source.parent / state_dir).resolve()
    return SiteSettings(
        station_key=key,
        server=str(_get(station, "server", "rtserve.iris.washington.edu:18000")),
        horizontals=bool(_get(station, "horizontals", True)),
        partner_key=partner,
        reach=str(_get(raw.get("reach", {}), "id", "TRISHULI-R07")),
        state_dir=state_dir,
        health_port=port,
        window_s=window_s,
        hop_s=hop_s,
        max_gap_fraction=gap,
        stale_feed_s=float(_get(feed, "stale_feed_s", 120.0)),
        source_path=source,
    )


def load_settings(path: str | Path | None = None) -> SiteSettings:
    """Read settings from a file, or the built in defaults when no path is given."""
    if path is None:
        return parse_settings(DEFAULT_SETTINGS_TOML)
    p = Path(path)
    return parse_settings(p.read_text(encoding="utf-8"), source=p)
