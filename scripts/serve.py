"""Local web interface for the GHADI pipeline — a browser you can test in.

Standard library only, fully offline. Serves a form; on each submit it runs one window
through ``ghadi.service.process_window`` and shows the decision, suppression, channels,
per-settlement lead times, and the emitted CAP alert.

    python scripts/serve.py          # then open http://localhost:8770

This is a testing surface, not the operational system: the live SeedLink/DHM feed
(issue 0.1) is still the missing piece, and no alert here is Actual/Public.
"""

from __future__ import annotations

import html
import sys
import urllib.parse
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ghadi.config import PRIMARY_STATION_LAT, PRIMARY_STATION_LON  # noqa: E402
from ghadi.hydro import synthetic_surge  # noqa: E402
from ghadi.service import GaugeObservation, WindowObservation, process_window  # noqa: E402
from ghadi.teleseism import Origin  # noqa: E402

PORT = 8770
DETECTED = datetime(2026, 8, 26, 2, 52, 24, tzinfo=UTC)
CASCADE = (4.9188, 1.8852)

_TIER_COLOR = {"WARNING": "#c0392b", "ADVISORY": "#d68910", "WATCH": "#2471a3", "NONE": "#566573"}


def _obs_gauge(times: np.ndarray, stage: np.ndarray, alive: bool) -> GaugeObservation:
    return GaugeObservation(times.tolist(), stage.tolist(), sensor_alive=alive, name="gauge_timure")


def _gauge(mode: str) -> GaugeObservation | None:
    if mode == "none":
        return None
    if mode == "quiet":
        times = np.arange(0.0, 3600.0, 60.0)
        stage = np.full_like(times, 2.0) + np.random.default_rng(7).normal(0, 0.01, times.size)
        return _obs_gauge(times, stage, alive=True)
    if mode == "dead":
        times, stage = synthetic_surge(destroy_at_s=300.0)
        return _obs_gauge(times, stage, alive=False)
    times, stage = synthetic_surge()
    return _obs_gauge(times, stage, alive=True)


def _run(q: dict[str, str]) -> str:
    lf_hf = float(q.get("lf_hf", CASCADE[0]))
    centroid = float(q.get("centroid", CASCADE[1]))
    gauge_mode = q.get("gauge", "surge")
    station_alive = q.get("station", "on") == "on"
    teleseism = q.get("teleseism", "") == "on"
    latency = float(q.get("latency", 60.0))

    origins: tuple[Origin, ...] = ()
    if teleseism:
        origins = (
            Origin(time_utc=DETECTED, latitude=PRIMARY_STATION_LAT, longitude=PRIMARY_STATION_LON,
                   magnitude=6.5, place="injected teleseism"),
        )

    obs = WindowObservation(
        window_start_utc=DETECTED - timedelta(seconds=120),
        detected_utc=DETECTED,
        segment_lf_hf=lf_hf,
        segment_centroid_hz=centroid,
        seismic_sensor_alive=station_alive,
        gauge=_gauge(gauge_mode),
        origins=origins,
        event_id="NPL-2026-08-26-BHOTEKOSHI-001",
    )
    outcome = process_window(
        obs, reach="TRISHULI-R07", model_version="sta_lta@v0.1.0+classify@v0.1.0",
        warning_latency_s=latency,
    )

    tier = outcome.decision.tier.value
    color = _TIER_COLOR.get(tier, "#566573")
    leads = ""
    if outcome.lead_times_min:
        rows = "".join(
            f"<tr><td>{html.escape(s)}</td><td class='num'>{v:.0f} min</td></tr>"
            for s, v in sorted(outcome.lead_times_min.items(), key=lambda kv: kv[1])
        )
        leads = f"<table class='lead'><tr><th>settlement</th><th>warning</th></tr>{rows}</table>"
    alert = (
        html.escape(outcome.alert_xml)
        if outcome.alert_xml
        else "(no alert — decision below threshold)"
    )
    alive = html.escape(", ".join(outcome.decision.channels_alive) or "none")
    dead = html.escape(", ".join(outcome.decision.channels_dead) or "none")

    return f"""
    <div class="result">
      <div class="tier" style="background:{color}">{tier}</div>
      <div class="meta">
        <b>fused probability</b> {outcome.decision.probability:.2f} &nbsp;·&nbsp;
        <b>alive</b> {alive} &nbsp;·&nbsp;
        <b>dead</b> {dead}
      </div>
      <div class="meta"><b>teleseism suppressed</b> {outcome.suppression.suppressed} —
        {html.escape(outcome.suppression.reason)}</div>
      <div class="meta"><b>rationale</b> {html.escape(outcome.decision.rationale)}</div>
      {leads}
      <details><summary>CAP alert (status=Test, scope=Restricted)</summary>
        <pre>{alert}</pre></details>
    </div>"""


def _page(q: dict[str, str]) -> str:
    def sel(name: str, val: str) -> str:
        return "selected" if q.get("gauge", "surge") == val else ""

    def chk(name: str, default: bool) -> str:
        present = "station" in q or "teleseism" in q or "lf_hf" in q
        on = q.get(name, "on" if (default and not present) else "") == "on"
        return "checked" if on else ""

    lf_hf = q.get("lf_hf", str(CASCADE[0]))
    centroid = q.get("centroid", str(CASCADE[1]))
    latency = q.get("latency", "60")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GHADI pipeline</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 15px/1.5 system-ui, sans-serif; max-width: 760px; margin: 2rem auto;
         padding: 0 1rem; }}
  h1 {{ font-size: 1.4rem; margin-bottom: .2rem; }}
  .sub {{ color: #888; margin-top: 0; font-size: .9rem; }}
  form {{ display: grid; grid-template-columns: 1fr 1fr; gap: .8rem 1.2rem;
          border: 1px solid #8884; border-radius: 10px; padding: 1.1rem; }}
  label {{ display: flex; flex-direction: column; font-size: .82rem; color: #999;
           gap: .25rem; }}
  input, select {{ font: inherit; padding: .4rem .5rem; border: 1px solid #8886;
                   border-radius: 6px; background: transparent; color: inherit; }}
  .row {{ flex-direction: row; align-items: center; gap: .5rem; }}
  button {{ grid-column: 1 / -1; padding: .6rem; font: inherit; font-weight: 600;
            border: 0; border-radius: 8px; background: #2471a3; color: #fff;
            cursor: pointer; }}
  .result {{ margin-top: 1.4rem; }}
  .tier {{ display: inline-block; color: #fff; font-weight: 700; padding: .3rem .9rem;
           border-radius: 6px; letter-spacing: .05em; }}
  .meta {{ margin: .5rem 0; font-size: .9rem; }}
  table.lead {{ border-collapse: collapse; margin: .8rem 0; }}
  table.lead th, table.lead td {{ border: 1px solid #8884; padding: .3rem .8rem;
                                  text-align: left; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  pre {{ background: #8881; padding: .8rem; border-radius: 8px; overflow-x: auto;
         font-size: .8rem; }}
  details summary {{ cursor: pointer; margin-top: .6rem; }}
</style></head><body>
<h1>GHADI — detection → decision → alert</h1>
<p class="sub">One window through the pipeline. Offline; no alert is Actual/Public.</p>
<form method="get">
  <label>seismic LF/HF <input name="lf_hf" value="{html.escape(lf_hf)}"></label>
  <label>seismic centroid (Hz) <input name="centroid" value="{html.escape(centroid)}"></label>
  <label>gauge
    <select name="gauge">
      <option value="surge" {sel('gauge','surge')}>surge (real flood)</option>
      <option value="quiet" {sel('gauge','quiet')}>quiet river</option>
      <option value="dead" {sel('gauge','dead')}>sensor died early</option>
      <option value="none" {sel('gauge','none')}>no gauge</option>
    </select></label>
  <label>warning latency (s)
    <input name="latency" type="number" value="{html.escape(latency)}"></label>
  <label class="row"><input type="checkbox" name="station" {chk('station', True)}>
    seismic station online</label>
  <label class="row"><input type="checkbox" name="teleseism" {chk('teleseism', False)}>
    inject distant M6.5 earthquake</label>
  <button type="submit">Run pipeline</button>
</form>
{_run(q)}
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path not in ("/", ""):
            self.send_response(404)
            self.end_headers()
            return
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        body = _page(q).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # quiet
        pass


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"GHADI interface on http://localhost:{PORT}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
