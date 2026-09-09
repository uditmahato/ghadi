"""Local web interface for the GHADI pipeline — a browser you can test in.

Standard library only, fully offline. Serves a form; on each submit it runs one window
through ``ghadi.service.process_window`` and shows the verdict, the evidence channels,
teleseism suppression, per-settlement lead times, and the emitted CAP alert.

    python scripts/serve.py          # then open http://localhost:8770

This is a testing surface, not the operational system: the live SeedLink/DHM feed
(issue 0.1) is still the missing piece, and no alert here is Actual/Public.
"""

from __future__ import annotations

import html
import sys
import urllib.parse
from dataclasses import dataclass
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
MAX_LEAD_MIN = 40.0  # scale for the lead-time bars (Bidur ~38 min is the far end)

_TIER = {
    "WARNING": ("#c0392b", "🔴", "Move people now — corroborated surge threat."),
    "ADVISORY": ("#d68910", "🟠", "Prepare and confirm — one line of evidence."),
    "WATCH": ("#2471a3", "🟡", "Keep watching — weak or single signal."),
    "NONE": ("#5d6d7e", "⚪", "No alert — nothing crossed the threshold."),
}

# One-click scenarios (label, query string, hint).
PRESETS = [
    ("2026 cascade", "lf_hf=4.9188&centroid=1.8852&gauge=surge&station=on", "the real event"),
    ("Earthquake + surge", "lf_hf=1.66&centroid=3.04&gauge=surge&station=on", "gauge carries it"),
    ("Teleseism", "lf_hf=4.9188&centroid=1.8852&gauge=none&teleseism=on", "distant quake"),
    ("Dead gauge", "lf_hf=1.66&centroid=3.04&gauge=dead", "sensor died"),
    ("Quiet day", "lf_hf=1.66&centroid=3.04&gauge=quiet", "nothing happening"),
    ("Slow pipeline", "lf_hf=4.9188&centroid=1.8852&gauge=surge&latency=600", "loses the race"),
]

CSS = """
:root { color-scheme: light dark; --bg:#f4f5f7; --card:#fff; --ink:#1a2027;
        --muted:#7a8896; --line:#e2e6ea; --accent:#2471a3; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14181d; --card:#1c2229; --ink:#e7ecf1; --muted:#8b98a6;
          --line:#2b333c; --accent:#4aa3df; } }
* { box-sizing: border-box; }
body { font: 15px/1.55 system-ui, -apple-system, Segoe UI, sans-serif;
       background: var(--bg); color: var(--ink); margin: 0; }
.wrap { max-width: 860px; margin: 0 auto; padding: 2rem 1.2rem 4rem; }
h1 { font-size: 1.5rem; margin: 0; letter-spacing: -.01em; }
.sub { color: var(--muted); margin: .3rem 0 1.4rem; font-size: .92rem; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
        padding: 1.3rem; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.presets { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1rem; }
.chip { text-decoration: none; color: var(--ink); background: var(--card);
        border: 1px solid var(--line); border-radius: 999px; padding: .38rem .85rem;
        font-size: .85rem; transition: .15s; }
.chip:hover { border-color: var(--accent); color: var(--accent); }
.chip small { color: var(--muted); }
form { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem 1.3rem; }
label { display: flex; flex-direction: column; gap: .3rem; font-size: .78rem;
        color: var(--muted); font-weight: 600; letter-spacing: .02em;
        text-transform: uppercase; }
input, select { font: inherit; padding: .5rem .6rem; border: 1px solid var(--line);
        border-radius: 9px; background: var(--bg); color: var(--ink); }
input:focus, select:focus { outline: 2px solid var(--accent); border-color: transparent; }
.toggle { flex-direction: row; align-items: center; gap: .55rem; text-transform: none;
        font-size: .9rem; color: var(--ink); font-weight: 500; }
.toggle input { width: 1.1rem; height: 1.1rem; accent-color: var(--accent); }
button { grid-column: 1 / -1; padding: .75rem; font: inherit; font-weight: 700;
        border: 0; border-radius: 10px; background: var(--accent); color: #fff;
        cursor: pointer; font-size: 1rem; }
button:hover { filter: brightness(1.06); }
.verdict { display: flex; align-items: center; gap: .9rem; margin: 1.5rem 0 0;
        padding: 1rem 1.2rem; border-radius: 14px; color: #fff; }
.verdict .big { font-size: 1.5rem; font-weight: 800; letter-spacing: .03em; }
.verdict .say { font-size: .92rem; opacity: .95; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1rem; }
.k { font-size: .72rem; color: var(--muted); text-transform: uppercase;
        letter-spacing: .04em; font-weight: 700; margin-bottom: .5rem; }
.meter { height: 10px; background: var(--line); border-radius: 999px; overflow: hidden; }
.meter > span { display: block; height: 100%; background: var(--accent); }
.pill { display: inline-block; padding: .2rem .6rem; border-radius: 999px;
        font-size: .82rem; font-weight: 600; margin: .15rem .25rem .15rem 0; }
.pill.alive { background: #1e8e4922; color: #1e8e49; }
.pill.dead { background: #c0392b22; color: #c0392b; }
.lead-row { display: grid; grid-template-columns: 90px 1fr 74px; align-items: center;
        gap: .7rem; margin: .5rem 0; }
.lead-row .name { font-size: .9rem; }
.bar { height: 22px; background: var(--line); border-radius: 7px; overflow: hidden; }
.bar > span { display: block; height: 100%; border-radius: 7px; }
.lead-row .val { text-align: right; font-variant-numeric: tabular-nums;
        font-weight: 700; font-size: .9rem; }
.note { font-size: .84rem; color: var(--muted); margin-top: .6rem; }
details { margin-top: 1rem; }
summary { cursor: pointer; font-weight: 600; font-size: .9rem; }
pre { background: var(--bg); border: 1px solid var(--line); padding: .9rem;
        border-radius: 10px; overflow-x: auto; font-size: .78rem; margin-top: .6rem; }
.banner { font-size: .8rem; color: var(--muted); margin-top: 2rem; text-align: center; }
@media (max-width: 620px) { form, .grid2 { grid-template-columns: 1fr; } }
"""


@dataclass
class Inputs:
    lf_hf: float
    centroid: float
    gauge: str
    station_alive: bool
    teleseism: bool
    latency: float


def _parse(q: dict[str, str]) -> Inputs:
    touched = bool(q)  # first load (no query) => use friendly defaults
    return Inputs(
        lf_hf=float(q.get("lf_hf", CASCADE[0])),
        centroid=float(q.get("centroid", CASCADE[1])),
        gauge=q.get("gauge", "surge"),
        station_alive=(q.get("station", "on") == "on") if touched else True,
        teleseism=q.get("teleseism", "") == "on",
        latency=float(q.get("latency", 60.0)),
    )


def _gauge(mode: str) -> GaugeObservation | None:
    if mode == "none":
        return None
    if mode == "quiet":
        times = np.arange(0.0, 3600.0, 60.0)
        stage = np.full_like(times, 2.0) + np.random.default_rng(7).normal(0, 0.01, times.size)
        alive = True
    elif mode == "dead":
        times, stage = synthetic_surge(destroy_at_s=300.0)
        alive = False
    else:
        times, stage = synthetic_surge()
        alive = True
    return GaugeObservation(times.tolist(), stage.tolist(), sensor_alive=alive, name="gauge_timure")


def _run(inp: Inputs):  # type: ignore[no-untyped-def]
    origins: tuple[Origin, ...] = ()
    if inp.teleseism:
        origins = (
            Origin(time_utc=DETECTED, latitude=PRIMARY_STATION_LAT, longitude=PRIMARY_STATION_LON,
                   magnitude=6.5, place="injected teleseism"),
        )
    obs = WindowObservation(
        window_start_utc=DETECTED - timedelta(seconds=120),
        detected_utc=DETECTED,
        segment_lf_hf=inp.lf_hf,
        segment_centroid_hz=inp.centroid,
        seismic_sensor_alive=inp.station_alive,
        gauge=_gauge(inp.gauge),
        origins=origins,
        event_id="NPL-2026-08-26-BHOTEKOSHI-001",
    )
    return process_window(
        obs, reach="TRISHULI-R07", model_version="sta_lta@v0.1.0+classify@v0.1.0",
        warning_latency_s=inp.latency,
    )


def _lead_bar(name: str, lead: float) -> str:
    if lead <= 0:
        color, width, val = "#c0392b", 6, f"{lead:.0f}m late"
    elif lead >= 10:
        color, width, val = "#1e8e49", min(100, lead / MAX_LEAD_MIN * 100), f"{lead:.0f} min"
    else:
        color, width, val = "#d68910", min(100, lead / MAX_LEAD_MIN * 100), f"{lead:.0f} min"
    return (
        f"<div class='lead-row'><div class='name'>{html.escape(name)}</div>"
        f"<div class='bar'><span style='width:{width}%;background:{color}'></span></div>"
        f"<div class='val'>{val}</div></div>"
    )


def _result(inp: Inputs) -> str:
    o = _run(inp)
    tier = o.decision.tier.value
    color, icon, say = _TIER[tier]
    p = o.decision.probability

    pills = "".join(f"<span class='pill alive'>{html.escape(c)}</span>"
                    for c in o.decision.channels_alive)
    pills += "".join(f"<span class='pill dead'>{html.escape(c)} ✕</span>"
                     for c in o.decision.channels_dead)
    pills = pills or "<span class='pill dead'>no live channel — blind</span>"

    leads = ""
    if o.lead_times_min:
        leads = "".join(_lead_bar(s, v)
                        for s, v in sorted(o.lead_times_min.items(), key=lambda kv: kv[1]))
        leads = (
            "<div class='card' style='margin-top:1rem'>"
            "<div class='k'>Minutes of warning</div>" + leads + "</div>"
        )

    supp = ""
    if o.suppression.suppressed:
        supp = (f"<div class='note'>🛰️ <b>Teleseism suppressed:</b> "
                f"{html.escape(o.suppression.reason)}</div>")

    alert = html.escape(o.alert_xml) if o.alert_xml else "No alert emitted (below threshold)."
    alert_block = (
        f"<details><summary>📋 CAP alert (status=Test · scope=Restricted)</summary>"
        f"<pre>{alert}</pre></details>"
    )

    return (
        f"<div class='verdict' style='background:{color}'>"
        f"<div style='font-size:1.8rem'>{icon}</div>"
        f"<div><div class='big'>{tier}</div><div class='say'>{html.escape(say)}</div></div></div>"
        f"<div class='grid2'>"
        f"<div class='card'><div class='k'>Fused confidence</div>"
        f"<div style='font-size:1.6rem;font-weight:800;margin-bottom:.5rem'>{p:.2f}</div>"
        f"<div class='meter'><span style='width:{p * 100:.0f}%'></span></div>"
        f"<div class='note'>{html.escape(o.decision.rationale)}</div></div>"
        f"<div class='card'><div class='k'>Evidence channels</div><div>{pills}</div>{supp}</div>"
        f"</div>{leads}<div class='card' style='margin-top:1rem'>{alert_block}</div>"
    )


def _form(inp: Inputs) -> str:
    def opt(val: str, text: str) -> str:
        s = "selected" if inp.gauge == val else ""
        return f"<option value='{val}' {s}>{text}</option>"

    presets = "".join(
        f"<a class='chip' href='/?{qs}'>{html.escape(lbl)} <small>· {html.escape(hint)}</small></a>"
        for lbl, qs, hint in PRESETS
    )
    st = "checked" if inp.station_alive else ""
    ts = "checked" if inp.teleseism else ""
    return (
        f"<div class='presets'>{presets}</div>"
        f"<div class='card'><form method='get'>"
        f"<label>Seismic LF/HF ratio<input name='lf_hf' value='{inp.lf_hf}'></label>"
        f"<label>Seismic centroid (Hz)<input name='centroid' value='{inp.centroid}'></label>"
        f"<label>Downstream gauge<select name='gauge'>"
        f"{opt('surge', 'Surge — real flood')}{opt('quiet', 'Quiet river')}"
        f"{opt('dead', 'Sensor died early')}{opt('none', 'No gauge')}</select></label>"
        f"<label>Warning latency (seconds)"
        f"<input name='latency' type='number' value='{inp.latency:.0f}'></label>"
        f"<label class='toggle'><input type='checkbox' name='station' {st}> "
        f"Seismic station online</label>"
        f"<label class='toggle'><input type='checkbox' name='teleseism' {ts}> "
        f"Inject distant M6.5 earthquake</label>"
        f"<button type='submit'>Run the pipeline ▸</button>"
        f"</form></div>"
    )


def _page(q: dict[str, str]) -> str:
    inp = _parse(q)
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>GHADI pipeline</title><style>" + CSS + "</style></head><body><div class='wrap'>"
        "<h1>GHADI &nbsp;·&nbsp; detection → decision → alert</h1>"
        "<p class='sub'>One window through the whole pipeline. Pick a scenario or tune the "
        "inputs. Fully offline — every alert stays <b>Test / Restricted</b>.</p>"
        + _form(inp) + _result(inp)
        + "<div class='banner'>GHADI testing interface · live SeedLink feed (issue 0.1) not "
          "wired · not an operational warning system</div>"
        "</div></body></html>"
    )


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

    def log_message(self, *args: object) -> None:
        pass


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"GHADI interface on http://localhost:{PORT}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
