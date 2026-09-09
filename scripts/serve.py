"""Local research dashboard for the GHADI pipeline.

Standard library only, fully offline. A window is run through
``ghadi.service.process_window`` and presented as a light, research-oriented dashboard:
simulation parameters on the left, the simulated decision and evidence on the right,
with scientific visualizations and research details below.

    python scripts/serve.py          # then open http://localhost:8770

This is an offline research simulation, not an operational warning system. The live
SeedLink/DHM feed (issue 0.1) is not wired; inputs shown here are synthetic, and every
alert payload stays status=Test, scope=Restricted.
"""

from __future__ import annotations

import html
import io
import json
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ghadi.config import DEFAULT, PRIMARY_STATION_LAT, PRIMARY_STATION_LON  # noqa: E402
from ghadi.hydro import detect_anomaly, rate_of_rise, synthetic_surge  # noqa: E402
from ghadi.service import GaugeObservation, WindowObservation, process_window  # noqa: E402
from ghadi.teleseism import Origin  # noqa: E402

PORT = 8770
EVENT_TIME = datetime(2026, 8, 26, 2, 52, 24, tzinfo=UTC)
CASCADE = (4.9188, 1.8852)
MAX_LEAD_MIN = 40.0
ACTIONABLE_MIN = DEFAULT.travel.actionable_lead_min if hasattr(DEFAULT, "travel") else 10.0
RATE_THRESHOLD = DEFAULT.hydro.rate_threshold_m_per_min
LF_HF_THRESHOLD = DEFAULT.classify.cascade_segment_lf_hf
CENTROID_THRESHOLD = DEFAULT.classify.cascade_segment_centroid_hz
WARNING_P = DEFAULT.fusion.warning_p
MIN_GROUPS = DEFAULT.fusion.min_groups_for_warning
MODEL_VERSION = "sta_lta@v0.1.0 + classify@v0.1.0 + fusion@v0.1.0"
REACH_ID = "TRISHULI-R07"
RIVER_SYSTEM = "Lhende Khola to Bhote Koshi to Trishuli"

# Result-state palette. Red/amber/green identify outcome states only.
STATE = {
    "WARNING": {"c": "#A52828", "bg": "#FFF1F0", "bd": "#E7C3BF", "label": "Warning"},
    "ADVISORY": {"c": "#8A5800", "bg": "#FFF7E6", "bd": "#E7D4A8", "label": "Advisory"},
    "WATCH": {"c": "#256A91", "bg": "#EAF3F8", "bd": "#C2D8E7", "label": "Watch"},
    "NONE": {"c": "#526174", "bg": "#F1F4F8", "bd": "#DCE3EB", "label": "No alert"},
}
STATE_MEANING = {
    "WARNING": "The selected inputs meet the configured warning criteria.",
    "ADVISORY": "One line of evidence indicates a possible surge. Confirmation is advised.",
    "WATCH": "A weak or single signal is present. Monitoring is advised.",
    "NONE": "No evidence crossed the configured decision threshold.",
}
SAMPLE_INSTRUCTION = {
    "WARNING": "Move away from the river channel to higher ground immediately.",
    "ADVISORY": "Prepare to move away from the river channel. Await confirmation.",
    "WATCH": "Monitor official channels. No action required at this time.",
    "NONE": "Monitor official channels. No action required at this time.",
}
BAR_BLUE, BAR_RED = "#256A91", "#A52828"

# Neutral scenario names with honest, provenance-aware explanations.
PRESETS = [
    (
        "2026 Bhote Koshi cascade",
        "lf_hf=4.9188&centroid=1.8852&gauge=surge&station=on",
        "Illustrative inputs based on the 26 Aug 2026 event",
    ),
    (
        "Regional earthquake with surge",
        "lf_hf=1.66&centroid=3.04&gauge=surge&station=on",
        "Earthquake-like seismic features, real gauge rise",
    ),
    (
        "Distant earthquake",
        "lf_hf=4.9188&centroid=1.8852&gauge=none&teleseism=on",
        "A teleseism the catalogue explains and sets aside",
    ),
    (
        "Gauge unavailable",
        "lf_hf=1.66&centroid=3.04&gauge=dead",
        "Downstream sensor stops reporting mid-event",
    ),
    (
        "Background conditions",
        "lf_hf=1.66&centroid=3.04&gauge=quiet",
        "Quiet seismic and river; no event",
    ),
    (
        "Increased processing latency",
        "lf_hf=4.9188&centroid=1.8852&gauge=surge&latency=600",
        "A slow pipeline erodes the lead time",
    ),
]
PARAM_KEYS = ("lf_hf", "centroid", "gauge", "station", "teleseism", "latency")
GAUGE_LABEL = {
    "surge": "Surge (flood rise)",
    "quiet": "Background conditions",
    "dead": "Sensor stops reporting",
    "none": "No gauge channel",
}
CHANNEL_LABEL = {"seismic": "Seismic station (NK.KKN)", "gauge_timure": "Timure gauge"}

CSS = """
:root {
  --bg:#F7F9FC; --panel:#FFFFFF; --ink:#172B4D; --muted:#526174;
  --line:#DCE3EB; --accent:#256A91; --accent-h:#1D5575; --sel:#EAF3F8;
}
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.5 "Inter","Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif; }
a { color:var(--accent); }
.tnum { font-variant-numeric:tabular-nums; }
.wrap { max-width:1240px; margin:0 auto; padding:0 32px; }
header.top { border-bottom:1px solid var(--line); background:var(--panel); }
header.top .row { display:flex; align-items:center; justify-content:space-between;
  gap:20px; flex-wrap:wrap; padding:14px 0; }
.brand { display:flex; align-items:baseline; gap:12px; }
.brand strong { font-size:1.3rem; font-weight:700; letter-spacing:-.01em; }
.brand span { color:var(--muted); font-size:.92rem; }
header nav { display:flex; gap:20px; font-size:.95rem; }
header nav a { text-decoration:none; color:var(--muted); }
header nav a:hover { color:var(--accent); }
.chip-badge { font-size:.8rem; color:var(--accent); background:var(--sel);
  border:1px solid #C2D8E7; border-radius:6px; padding:4px 10px; }
.notice { background:var(--sel); border:1px solid #C2D8E7; border-radius:8px;
  padding:12px 16px; margin:20px 0; font-size:.92rem; }
.notice b { color:var(--accent); }
.title h1 { font-size:1.9rem; font-weight:700; margin:8px 0 4px; letter-spacing:-.01em; }
.title p { color:var(--muted); margin:0 0 8px; max-width:70ch; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:22px; box-shadow:0 1px 2px rgba(23,43,77,.04); }
h2.sec { font-size:1.2rem; font-weight:600; margin:0 0 4px; }
p.lede { color:var(--muted); font-size:.92rem; margin:0 0 16px; }
.workspace { display:grid; grid-template-columns:360px 1fr; gap:24px; margin-top:8px;
  align-items:start; }
label.field { display:block; margin-bottom:16px; }
label.field .lab { font-size:.86rem; font-weight:600; margin-bottom:4px; display:block; }
label.field .help { font-size:.8rem; color:var(--muted); margin-top:4px; }
input[type=text], input[type=number], select { width:100%; height:44px; font:inherit;
  font-size:.95rem; padding:0 12px; border:1px solid var(--line); border-radius:8px;
  background:#FCFDFE; color:var(--ink); }
input:focus-visible, select:focus-visible, a:focus-visible, button:focus-visible,
.preset:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.err input, .err select { border-color:var(--accent); }
.errmsg { color:#A52828; font-size:.82rem; margin-top:4px; }
.check { display:flex; align-items:center; gap:9px; margin-bottom:14px; font-size:.94rem; }
.check input { width:18px; height:18px; }
.presets { display:grid; gap:8px; margin-bottom:18px; }
.preset { text-align:left; background:#FCFDFE; border:1px solid var(--line);
  border-radius:8px; padding:10px 12px; cursor:pointer; text-decoration:none; color:inherit;
  display:block; }
.preset:hover { border-color:var(--accent); }
.preset[aria-current=true] { background:var(--sel); border-color:var(--accent); }
.preset b { font-size:.94rem; } .preset small { color:var(--muted); display:block; }
.btn { font:inherit; font-size:.95rem; height:44px; padding:0 18px; border-radius:8px;
  border:1px solid var(--line); background:#fff; color:var(--ink); cursor:pointer;
  text-decoration:none; display:inline-flex; align-items:center; }
.btn.primary { background:var(--accent); border-color:var(--accent); color:#fff;
  font-weight:600; width:100%; justify-content:center; }
.btn.primary:hover { background:var(--accent-h); }
.controls { display:flex; gap:10px; margin-top:6px; }
.controls .btn:not(.primary) { flex:0 0 auto; }
.stale { background:#FFF7E6; border:1px solid #E7D4A8; color:#8A5800; border-radius:8px;
  padding:10px 14px; margin-bottom:14px; font-size:.9rem; }
.outcome { border-radius:10px; padding:18px 20px; display:flex; gap:14px; }
.outcome .ic { width:26px; height:26px; flex:0 0 auto; border-radius:50%; margin-top:2px; }
.outcome .tag { font-size:.8rem; font-weight:600; text-transform:uppercase;
  letter-spacing:.04em; }
.outcome h3 { margin:2px 0 4px; font-size:1.4rem; }
.outcome p { margin:0; font-size:.96rem; }
.sample { margin-top:12px; background:#fff; border:1px dashed var(--line); border-radius:8px;
  padding:10px 12px; }
.sample .k { font-size:.78rem; font-weight:600; color:var(--muted);
  text-transform:uppercase; letter-spacing:.04em; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-top:18px; }
.metric .k { font-size:.86rem; color:var(--muted); margin-bottom:6px; }
.metric .v { font-size:2rem; font-weight:700; line-height:1.1; }
.kvrow { display:flex; justify-content:space-between; font-size:.9rem; padding:3px 0;
  border-bottom:1px solid #EEF1F6; }
.kvrow span:last-child { font-weight:600; }
.meter { height:10px; background:#EEF1F6; border-radius:6px; margin:10px 0 4px;
  position:relative; }
.meter > span { display:block; height:100%; border-radius:6px; background:var(--accent); }
.meter .thr { position:absolute; top:-3px; bottom:-3px; width:2px; background:var(--ink); }
.scale-lab { display:flex; justify-content:space-between; font-size:.75rem;
  color:var(--muted); }
.chan { border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin:8px 0;
  display:flex; align-items:center; gap:12px; }
.dot { width:10px; height:10px; border-radius:50%; flex:0 0 auto; }
.tagpill { font-size:.76rem; padding:2px 8px; border-radius:5px; margin-left:auto;
  white-space:nowrap; }
.pos { background:#EDF7F0; color:#236444; } .neg { background:#F1F4F8; color:#526174; }
.off { background:#FFF1F0; color:#A52828; }
.section { margin-top:26px; }
.plots { display:grid; grid-template-columns:1fr 1fr; gap:22px; }
figure { margin:0; } figcaption { font-size:.82rem; color:var(--muted); margin-top:6px; }
.plot h3 { font-size:1rem; margin:0 0 4px; }
svg.chart { width:100%; height:auto; display:block; border:1px solid var(--line);
  border-radius:8px; background:#fff; }
.lead-row { display:grid; grid-template-columns:150px 1fr 70px; gap:12px; align-items:center;
  margin:9px 0; }
.lead-row .bar { height:20px; background:#EEF1F6; border-radius:5px; position:relative; }
.lead-row .bar > span { display:block; height:100%; border-radius:5px; }
.lead-row .bar .mark { position:absolute; top:-4px; bottom:-4px; width:2px;
  background:var(--ink); }
.lead-row .val { text-align:right; font-weight:600; }
.axis { display:grid; grid-template-columns:150px 1fr 70px; gap:12px; margin-top:4px;
  font-size:.75rem; color:var(--muted); }
.axis .ticks { display:flex; justify-content:space-between; }
details.d { border:1px solid var(--line); border-radius:8px; margin-bottom:10px;
  background:#FCFDFE; }
details.d > summary { cursor:pointer; font-weight:600; padding:13px 16px; font-size:.98rem; }
details.d[open] > summary { border-bottom:1px solid var(--line); }
details.d .body { padding:8px 16px 16px; font-size:.92rem; color:#2C3A55; }
table.kv { border-collapse:collapse; width:100%; font-size:.9rem; }
table.kv td { border-bottom:1px solid var(--line); padding:8px 4px; vertical-align:top; }
table.kv td:first-child { color:var(--muted); width:42%; }
code, pre { font-family:"SF Mono",Consolas,Menlo,monospace; }
pre { background:#0F1B2D; color:#D7E3F4; padding:14px; border-radius:8px; overflow:auto;
  font-size:.8rem; line-height:1.5; max-height:340px; }
.syn { color:#8A5800; } .obs { color:#236444; }
footer { border-top:1px solid var(--line); margin-top:40px; padding:20px 0 40px;
  color:var(--muted); font-size:.85rem; }
@media (max-width:900px) { .workspace, .grid2, .plots { grid-template-columns:1fr; } }
@media (prefers-reduced-motion:reduce) {
  html { scroll-behavior:auto; } * { transition:none!important; } }
"""


# --------------------------------------------------------------------------------------
# Inputs, parsing and validation
# --------------------------------------------------------------------------------------
@dataclass
class Inputs:
    lf_hf: float
    centroid: float
    gauge: str
    station_alive: bool
    teleseism: bool
    latency: float


def _scenario_name(q: dict[str, str], ran: bool) -> str:
    if not ran:
        return "Not run"
    now = {k: q.get(k, "") for k in PARAM_KEYS}
    for label, qs, _ in PRESETS:
        preset = {k: v for k, v in urllib.parse.parse_qsl(qs)}
        norm = {k: preset.get(k, "") for k in PARAM_KEYS}
        # Checkboxes: absent means off in both.
        if now == norm:
            return label
    return "Modified scenario"


def _validate(q: dict[str, str]) -> tuple[Inputs | None, dict[str, str]]:
    errors: dict[str, str] = {}

    def num(key: str, default: float, lo: float, hi: float, allow_lo_eq: bool = True) -> float:
        raw = q.get(key)
        if raw is None or raw == "":
            return default
        try:
            v = float(raw)
        except ValueError:
            errors[key] = "Enter a number."
            return default
        if v < lo or (v == lo and not allow_lo_eq) or v > hi:
            bound = f"{lo:g} to {hi:g}"
            errors[key] = f"Must be within {bound}."
        return v

    lf_hf = num("lf_hf", CASCADE[0], 0.0, 1000.0)
    centroid = num("centroid", CASCADE[1], 0.0, 25.0, allow_lo_eq=False)
    latency = num("latency", 60.0, 0.0, 100000.0)
    gauge = q.get("gauge", "surge")
    if gauge not in GAUGE_LABEL:
        errors["gauge"] = "Unknown gauge condition."
        gauge = "surge"
    if errors:
        return None, errors
    touched = bool(q)
    return (
        Inputs(
            lf_hf=lf_hf,
            centroid=centroid,
            gauge=gauge,
            station_alive=(q.get("station", "") == "on") if touched else True,
            teleseism=q.get("teleseism", "") == "on",
            latency=latency,
        ),
        errors,
    )


def _gauge_arrays(mode: str):  # type: ignore[no-untyped-def]
    if mode == "none":
        return None
    if mode == "quiet":
        times = np.arange(0.0, 3600.0, 60.0)
        stage = np.full_like(times, 2.0) + np.random.default_rng(7).normal(0, 0.01, times.size)
        return times, stage, True
    if mode == "dead":
        times, stage = synthetic_surge(destroy_at_s=300.0)
        return times, stage, False
    times, stage = synthetic_surge()
    return times, stage, True


def _gauge_obs(mode: str) -> GaugeObservation | None:
    arr = _gauge_arrays(mode)
    if arr is None:
        return None
    times, stage, alive = arr
    return GaugeObservation(times.tolist(), stage.tolist(), sensor_alive=alive, name="gauge_timure")


def _run(inp: Inputs):  # type: ignore[no-untyped-def]
    origins: tuple[Origin, ...] = ()
    if inp.teleseism:
        origins = (
            Origin(
                time_utc=EVENT_TIME,
                latitude=PRIMARY_STATION_LAT,
                longitude=PRIMARY_STATION_LON,
                magnitude=6.5,
                place="injected distant earthquake",
            ),
        )
    obs = WindowObservation(
        window_start_utc=EVENT_TIME - timedelta(seconds=120),
        detected_utc=EVENT_TIME,
        segment_lf_hf=inp.lf_hf,
        segment_centroid_hz=inp.centroid,
        seismic_sensor_alive=inp.station_alive,
        gauge=_gauge_obs(inp.gauge),
        origins=origins,
        event_id="NPL-2026-08-26-BHOTEKOSHI-001",
    )
    return process_window(
        obs, reach=REACH_ID, model_version=MODEL_VERSION, warning_latency_s=inp.latency
    )


def _qs(inp: Inputs) -> str:
    return urllib.parse.urlencode(
        {
            "lf_hf": inp.lf_hf,
            "centroid": inp.centroid,
            "gauge": inp.gauge,
            "station": "on" if inp.station_alive else "",
            "teleseism": "on" if inp.teleseism else "",
            "latency": f"{inp.latency:.0f}",
        }
    )


# --------------------------------------------------------------------------------------
# Charts (SVG)
# --------------------------------------------------------------------------------------
def _scalar_bullet(value: float, thr: float, meets_high: bool, unit: str) -> str:
    """A scalar comparison of one feature against its threshold (no fabricated series)."""
    w, h = 520, 66
    lo = 0.0
    hi = max(value, thr) * 1.25 + 0.5
    meets = (value >= thr) if meets_high else (value <= thr)

    def px(v: float) -> float:
        return 40 + (v - lo) / (hi - lo) * (w - 60)

    good = "#236444" if meets else "#A52828"
    parts = [f"<svg class='chart' viewBox='0 0 {w} {h}' role='img'>"]
    parts.append(f"<line x1='40' y1='40' x2='{w - 20}' y2='40' stroke='#DCE3EB'/>")
    parts.append(
        f"<rect x='40' y='34' width='{px(value) - 40:.1f}' height='12' rx='2' fill='{good}'/>"
    )
    parts.append(
        f"<line x1='{px(thr):.1f}' y1='24' x2='{px(thr):.1f}' y2='52' stroke='#172B4D' "
        f"stroke-width='2' stroke-dasharray='4 3'/>"
    )
    parts.append(
        f"<text x='{px(thr):.1f}' y='18' text-anchor='middle' font-size='11' fill='#172B4D'>"
        f"threshold {thr:.2f}{html.escape(unit)}</text>"
    )
    parts.append(
        f"<text x='40' y='62' font-size='11' fill='#526174'>{lo:.0f}</text>"
        f"<text x='{w - 20}' y='62' text-anchor='end' font-size='11' fill='#526174'>"
        f"{hi:.1f}{html.escape(unit)}</text>"
    )
    parts.append(
        f"<text x='{px(value):.1f}' y='30' text-anchor='middle' font-size='12' "
        f"font-weight='700' fill='{good}'>{value:.2f}{html.escape(unit)}</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _timeseries(xs, ys, xlabel, ylabel, threshold, thr_label, vline, vline_label, yfmt):  # type: ignore[no-untyped-def]
    w, h = 560, 230
    pl, pr, pt, pb = 58, 16, 16, 44
    xlo, xhi = float(min(xs)), float(max(xs))
    ylo = min(0.0, float(min(ys)))
    yhi = max(float(max(ys)), threshold if threshold is not None else float(max(ys)))
    if yhi <= ylo:
        yhi = ylo + 1

    def px(x: float) -> float:
        return pl + (x - xlo) / (xhi - xlo) * (w - pl - pr)

    def py(y: float) -> float:
        return h - pb - (y - ylo) / (yhi - ylo) * (h - pt - pb)

    p = [f"<svg class='chart' viewBox='0 0 {w} {h}' role='img'>"]
    for i in range(5):
        yt = ylo + (yhi - ylo) * i / 4
        y = py(yt)
        p.append(f"<line x1='{pl}' y1='{y:.1f}' x2='{w - pr}' y2='{y:.1f}' stroke='#EEF1F6'/>")
        p.append(
            f"<text x='{pl - 8}' y='{y + 4:.1f}' text-anchor='end' font-size='11' "
            f"fill='#526174'>{yfmt.format(yt)}</text>"
        )
    for i in range(5):
        xt = xlo + (xhi - xlo) * i / 4
        p.append(
            f"<text x='{px(xt):.1f}' y='{h - pb + 18}' text-anchor='middle' font-size='11' "
            f"fill='#526174'>{xt:.0f}</text>"
        )
    p.append(f"<line x1='{pl}' y1='{pt}' x2='{pl}' y2='{h - pb}' stroke='#B7C1D1'/>")
    p.append(f"<line x1='{pl}' y1='{h - pb}' x2='{w - pr}' y2='{h - pb}' stroke='#B7C1D1'/>")
    if threshold is not None:
        yt = py(threshold)
        p.append(
            f"<line x1='{pl}' y1='{yt:.1f}' x2='{w - pr}' y2='{yt:.1f}' stroke='#A52828' "
            f"stroke-width='1.3' stroke-dasharray='5 4'/>"
        )
        p.append(
            f"<text x='{w - pr}' y='{yt - 5:.1f}' text-anchor='end' font-size='11' "
            f"fill='#A52828'>{html.escape(thr_label)}</text>"
        )
    if vline is not None and xlo <= vline <= xhi:
        xv = px(vline)
        p.append(
            f"<line x1='{xv:.1f}' y1='{pt}' x2='{xv:.1f}' y2='{h - pb}' stroke='#256A91' "
            f"stroke-width='1.2' stroke-dasharray='4 3'/>"
        )
        p.append(
            f"<text x='{xv + 4:.1f}' y='{pt + 12}' font-size='11' fill='#256A91'>"
            f"{html.escape(vline_label)}</text>"
        )
    pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys, strict=True))
    p.append(f"<polyline points='{pts}' fill='none' stroke='#256A91' stroke-width='1.6'/>")
    p.append(
        f"<text x='{(w + pl) / 2:.0f}' y='{h - 6}' text-anchor='middle' font-size='11.5' "
        f"fill='#172B4D'>{html.escape(xlabel)}</text>"
    )
    p.append(
        f"<text transform='translate(15,{(h - pb + pt) / 2:.0f}) rotate(-90)' "
        f"text-anchor='middle' font-size='11.5' fill='#172B4D'>{html.escape(ylabel)}</text>"
    )
    p.append("</svg>")
    return "".join(p)


# --------------------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------------------
def _outcome_panel(o) -> str:  # type: ignore[no-untyped-def]
    tier = o.decision.tier.value
    s = STATE[tier]
    return (
        f"<div class='outcome' style='background:{s['bg']};border:1px solid {s['bd']};"
        f"border-left:4px solid {s['c']}'>"
        f"<div class='ic' style='background:{s['c']}' aria-hidden='true'></div><div>"
        f"<div class='tag' style='color:{s['c']}'>Simulated outcome</div>"
        f"<h3 style='color:{s['c']}'>{s['label']}</h3>"
        f"<p>{html.escape(STATE_MEANING[tier])}</p>"
        f"<div class='sample'><div class='k'>Sample alert message (illustrative only)</div>"
        f"{html.escape(SAMPLE_INSTRUCTION[tier])}</div></div></div>"
    )


def _confidence(o) -> str:  # type: ignore[no-untyped-def]
    p = o.decision.probability
    groups = o.decision.independent_groups
    width = min(100, p * 100)
    thr_x = WARNING_P * 100
    return (
        "<div class='panel metric'><div class='k'>Fused confidence score</div>"
        f"<div class='v tnum'>{p:.2f}</div>"
        f"<div class='meter'><span style='width:{width:.0f}%'></span>"
        f"<span class='thr' style='left:{thr_x:.0f}%'></span></div>"
        f"<div class='scale-lab'><span>0.00</span><span>threshold {WARNING_P:.2f}</span>"
        "<span>1.00</span></div>"
        f"<div class='kvrow'><span>Configured warning threshold</span>"
        f"<span class='tnum'>{WARNING_P:.2f}</span></div>"
        f"<div class='kvrow'><span>Supporting evidence groups</span>"
        f"<span class='tnum'>{groups} of {MIN_GROUPS} required</span></div>"
        "<p class='lede' style='margin-top:12px'>Combined across independent evidence sources "
        "(noisy-OR). Calibration: not calibrated. The operating points are assumed, based on a "
        "single confirmed event (n=1), so this is a decision score, not a validated probability."
        "</p></div>"
    )


def _channels(o) -> str:  # type: ignore[no-untyped-def]
    rows = ""
    for ch in o.channels:
        name = CHANNEL_LABEL.get(ch.name, ch.name)
        supports = ch.probability >= 0.5 and ch.alive
        if not ch.alive:
            dot, tag, tcls = "#A52828", "Unavailable", "off"
        elif supports:
            dot, tag, tcls = "#236444", "Supports outcome", "pos"
        else:
            dot, tag, tcls = "#526174", "Does not support", "neg"
        rows += (
            f"<div class='chan'><span class='dot' style='background:{dot}'></span>"
            f"<div><b>{html.escape(name)}</b><div class='lede' style='margin:2px 0 0'>"
            f"{html.escape(ch.detail)}</div></div>"
            f"<span class='tagpill {tcls}'>{tag}</span></div>"
        )
    if not rows:
        rows = "<p class='lede'>No evidence channels in this scenario.</p>"
    supp = ""
    if o.suppression.suppressed:
        supp = (
            "<p class='lede' style='margin-top:10px'>Seismic channel set aside as a distant "
            f"earthquake: {html.escape(o.suppression.reason)}</p>"
        )
    return f"<div class='panel'><h2 class='sec'>Evidence channels</h2>{rows}{supp}</div>"


def _seismic_evidence(inp: Inputs, o) -> str:  # type: ignore[no-untyped-def]
    lf = _scalar_bullet(inp.lf_hf, LF_HF_THRESHOLD, meets_high=True, unit="")
    cen = _scalar_bullet(inp.centroid, CENTROID_THRESHOLD, meets_high=False, unit=" Hz")
    lf_ok = inp.lf_hf >= LF_HF_THRESHOLD
    cen_ok = inp.centroid <= CENTROID_THRESHOLD
    verdict = "meets both criteria" if (lf_ok and cen_ok) else "does not meet both criteria"
    online = "online" if inp.station_alive else "offline"
    return (
        "<div class='plot'><h3>Seismic features (scalar comparison)</h3>"
        "<p class='lede'>The classifier decides on two scalar spectral features over the 120 s "
        "segment, not a waveform, so these are shown as value-versus-threshold comparisons "
        f"rather than a trace. Station is {online}; this window {verdict}.</p>"
        "<figure><figcaption>Low/high frequency ratio. Mass-movement-like when at or above the "
        f"threshold. Value {inp.lf_hf:.2f}, threshold {LF_HF_THRESHOLD:.2f}.</figcaption>"
        f"{lf}</figure>"
        "<figure style='margin-top:12px'><figcaption>Spectral centroid (Hz). Mass-movement-like "
        f"when at or below the threshold. Value {inp.centroid:.2f} Hz, threshold "
        f"{CENTROID_THRESHOLD:.2f} Hz.</figcaption>{cen}</figure></div>"
    )


def _gauge_evidence(inp: Inputs) -> str:
    arr = _gauge_arrays(inp.gauge)
    if arr is None:
        return (
            "<div class='plot'><h3>Downstream gauge</h3>"
            "<p class='lede'>No gauge channel is present in this scenario, so there is no "
            "rate-of-rise series to show.</p></div>"
        )
    times, stage, alive = arr
    rate = rate_of_rise(times, stage, DEFAULT.hydro.rate_window_s)
    anomaly = detect_anomaly(times, stage)
    vmin = (anomaly.time_s / 60.0) if anomaly.time_s is not None else None
    svg = _timeseries(
        (times / 60.0).tolist(),
        rate.tolist(),
        "Time since window start (min)",
        "Rate of rise (m/min)",
        RATE_THRESHOLD,
        f"threshold {RATE_THRESHOLD:.2f} m/min",
        vmin,
        "detected",
        "{:.2f}",
    )
    peak = float(stage.max() - stage.min())
    life = "sensor continued reporting" if alive else "sensor stopped reporting at 300 s"
    det = f"at {anomaly.time_s / 60:.1f} min" if anomaly.time_s is not None else "not triggered"
    return (
        "<div class='plot'><h3>Downstream gauge rate of rise "
        "<span class='syn'>(synthetic)</span></h3>"
        "<figure><figcaption>Time basis: seconds since window start, shown in minutes. "
        f"Peak stage change {peak:.1f} m; {life}; anomaly {det}. Threshold "
        f"{RATE_THRESHOLD:.2f} m/min (red dashed).</figcaption>{svg}</figure></div>"
    )


def _warning_chart(o) -> str:  # type: ignore[no-untyped-def]
    if not o.lead_times_min:
        return (
            "<div class='panel section'><h2 class='sec'>Estimated warning lead time</h2>"
            "<p class='lede'>No lead-time estimate is available for this outcome.</p></div>"
        )
    mark = ACTIONABLE_MIN / MAX_LEAD_MIN * 100
    rows = ""
    for name, lead in sorted(o.lead_times_min.items(), key=lambda kv: kv[1]):
        if lead <= 0:
            color, width = BAR_RED, 3
            val = f"{lead:.0f} min"
        else:
            color, width = BAR_BLUE, min(100, lead / MAX_LEAD_MIN * 100)
            val = f"{lead:.0f} min"
        rows += (
            f"<div class='lead-row'><div>{html.escape(name)}</div>"
            f"<div class='bar'><span style='width:{width}%;background:{color}'></span>"
            f"<span class='mark' style='left:{mark:.0f}%'></span></div>"
            f"<div class='val tnum'>{val}</div></div>"
        )
    ticks = "".join(f"<span>{t}</span>" for t in (0, 10, 20, 30, 40))
    return (
        "<div class='panel section' id='warning'>"
        "<h2 class='sec'>Estimated warning lead time</h2>"
        "<p class='lede'>Estimated minutes between an issued alert and surge arrival at each "
        "settlement, on a shared 0 to 40 minute axis. Bars are blue; the vertical marker at "
        f"{ACTIONABLE_MIN:.0f} minutes is the configured lead considered potentially actionable. "
        "A red bar and a negative value mean the alert would follow the water. Basis: a "
        "single-event travel-time model calibrated on the 26 Aug 2026 event (n=1), not a "
        f"hydraulic model.</p><div>{rows}</div>"
        f"<div class='axis'><div></div><div class='ticks'>{ticks}</div>"
        "<div style='text-align:right'>min</div></div></div>"
    )


def _cap_summary(o) -> str:  # type: ignore[no-untyped-def]
    if not o.alert_xml:
        return "<p class='lede'>No alert payload is generated for this outcome.</p>"
    import xml.etree.ElementTree as ET

    ns = {"c": "urn:oasis:names:tc:emergency:cap:1.2"}
    root = ET.fromstring(o.alert_xml)

    def g(tag: str) -> str:
        el = root.find(f".//c:{tag}", ns)
        return el.text if el is not None and el.text else "n/a"

    summary = (
        "<table class='kv'>"
        f"<tr><td>Status</td><td>{html.escape(g('status'))}</td></tr>"
        f"<tr><td>Scope</td><td>{html.escape(g('scope'))}</td></tr>"
        f"<tr><td>Event</td><td>{html.escape(g('event'))}</td></tr>"
        f"<tr><td>Identifier</td><td><code>{html.escape(g('identifier'))}</code></td></tr>"
        f"<tr><td>Generated</td><td class='tnum'>{html.escape(g('sent'))}</td></tr></table>"
        "<p class='lede' style='margin-top:8px'>This payload is a simulation record. Copy and "
        "download do not transmit it anywhere.</p>"
    )
    raw = html.escape(o.alert_xml)
    return (
        summary + "<div class='controls' style='margin:10px 0'>"
        "<button class='btn' type='button' onclick='copyCap()'>Copy payload</button>"
        f"<a class='btn' href='/export?{{QS}}&amp;format=cap'>Download XML</a></div>"
        f"<pre id='cap'>{raw}</pre>"
    )


def _details(inp: Inputs, o, ran: bool) -> str:  # type: ignore[no-untyped-def]
    run_ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    cap = _cap_summary(o).replace("{QS}", _qs(inp)) if ran else ""
    gauge_prov = {
        "surge": "synthetic surge, Trishuli reference of 9 m over 30 minutes",
        "quiet": "synthetic quiet river",
        "dead": "synthetic surge truncated at 300 s (sensor loss)",
        "none": "no gauge channel",
    }[inp.gauge]
    return (
        "<div class='panel section' id='methodology'>"
        "<h2 class='sec'>Research details</h2>"
        "<p class='lede'>Reasoning, sources, and limits for this run.</p>"
        "<details class='d'><summary>Decision logic</summary><div class='body'>"
        "<p>A seismic window is classified as mass-movement-like only when the low/high "
        f"spectral ratio is at least {LF_HF_THRESHOLD:.2f} <b>and</b> the spectral centroid is "
        f"at most {CENTROID_THRESHOLD:.2f} Hz. A distant earthquake whose catalogued arrival "
        "explains the onset is set aside. The gauge fires when rate of rise exceeds "
        f"{RATE_THRESHOLD:.2f} m/min. Available channels are combined by noisy-OR across "
        f"independent sources; a Warning requires a fused score of at least {WARNING_P:.2f} with "
        f"at least {MIN_GROUPS} independent groups.</p></div></details>"
        "<details class='d' id='references'><summary>Data sources and provenance</summary>"
        "<div class='body'><ul>"
        "<li>Seismic: open FDSN broadband stations (NK.KKN, IO.EVN). In this simulation the "
        "seismic features are <span class='syn'>synthetic inputs</span>, not recorded data.</li>"
        "<li>Gauge: Nepal Department of Hydrology and Meteorology. A data-sharing agreement is "
        "not in place, so the gauge series here is <span class='syn'>synthetic</span>.</li>"
        "<li>Travel times: calibrated on the single 26 Aug 2026 event (n=1). No hydraulic "
        "model. External citations are not included.</li></ul></div></details>"
        "<details class='d'><summary>Assumptions and limitations</summary><div class='body'>"
        "<ul><li>Positive class is one confirmed event (n=1); confidence values are assumed "
        "operating points, not calibrated, and no uncertainty interval is claimed.</li>"
        "<li>Spectral overlap with real earthquakes is about 17% at this operating point.</li>"
        "<li>The live SeedLink feed is not wired (issue 0.1); this is not operational.</li>"
        "</ul></div></details>"
        "<details class='d'><summary>Model and configuration</summary><div class='body'>"
        "<table class='kv'>"
        f"<tr><td>Model version</td><td>{html.escape(MODEL_VERSION)}</td></tr>"
        f"<tr><td>River reach</td><td>{REACH_ID} ({html.escape(RIVER_SYSTEM)})</td></tr>"
        f"<tr><td>Seismic input</td><td><span class='syn'>synthetic</span> LF/HF "
        f"{inp.lf_hf:.2f}, centroid {inp.centroid:.2f} Hz, station "
        f"{'online' if inp.station_alive else 'offline'}</td></tr>"
        f"<tr><td>Gauge input</td><td><span class='syn'>{html.escape(gauge_prov)}</span></td></tr>"
        f"<tr><td>Distant earthquake</td><td>{'1 injected M6.5' if inp.teleseism else 'none'}"
        "</td></tr>"
        f"<tr><td>Warning latency</td><td class='tnum'>{inp.latency:.0f} s</td></tr>"
        f"<tr><td>Run generated</td><td class='tnum'>{run_ts}</td></tr>"
        "</table></div></details>"
        f"<details class='d'><summary>Alert payload (CAP 1.2)</summary><div class='body'>{cap}"
        "</div></details></div>"
    )


def _form(inp: Inputs, errors: dict[str, str], scenario: str) -> str:
    def opt(val: str) -> str:
        sel = "selected" if inp.gauge == val else ""
        return f"<option value='{val}' {sel}>{html.escape(GAUGE_LABEL[val])}</option>"

    def field(key: str, label: str, help_text: str, kind: str, value: str) -> str:
        cls = "field err" if key in errors else "field"
        err = (
            f"<div class='errmsg' role='alert'>{html.escape(errors[key])}</div>"
            if key in errors
            else ""
        )
        inp_html = (
            f"<select name='{key}'>{value}</select>"
            if kind == "select"
            else f"<input type='{kind}' name='{key}' value='{html.escape(value)}' "
            f"aria-describedby='{key}-h'>"
        )
        return (
            f"<label class='{cls}'><span class='lab'>{html.escape(label)}</span>{inp_html}"
            f"<span class='help' id='{key}-h'>{html.escape(help_text)}</span>{err}</label>"
        )

    presets = ""
    for label, qs, desc in PRESETS:
        cur = "true" if scenario == label else "false"
        presets += (
            f"<a class='preset' href='/?{qs}' aria-current='{cur}'>"
            f"<b>{html.escape(label)}</b><small>{html.escape(desc)}</small></a>"
        )
    gauge_opts = opt("surge") + opt("quiet") + opt("dead") + opt("none")
    st = "checked" if inp.station_alive else ""
    ts = "checked" if inp.teleseism else ""
    return (
        "<div class='panel'><h2 class='sec'>Scenario</h2>"
        "<p class='lede'>Select a preset, then adjust parameters as needed.</p>"
        f"<div class='presets'>{presets}</div>"
        "<h2 class='sec' style='margin-top:6px'>Simulation parameters</h2>"
        "<form method='get' id='sim'>"
        + field(
            "lf_hf",
            "Seismic LF/HF ratio",
            "Low-frequency over high-frequency energy. Higher indicates a slower source.",
            "text",
            f"{inp.lf_hf}",
        )
        + field(
            "centroid",
            "Seismic centroid (Hz)",
            "Average spectral frequency. Lower indicates a slower, mass-movement-like source.",
            "text",
            f"{inp.centroid}",
        )
        + field(
            "gauge",
            "Downstream gauge condition",
            "State of the downstream river gauge.",
            "select",
            gauge_opts,
        )
        + field(
            "latency",
            "Warning latency (seconds)",
            "Time from initiation to an issued alert.",
            "number",
            f"{inp.latency:.0f}",
        )
        + f"<label class='check'><input type='checkbox' name='station' {st}> "
        "Seismic station available</label>"
        + f"<label class='check'><input type='checkbox' name='teleseism' {ts}> "
        "Inject a distant earthquake</label>"
        "<div class='controls'><button class='btn primary' type='submit'>Run simulation</button>"
        "<a class='btn' href='/'>Reset</a></div>"
        "</form></div>"
    )


def _header() -> str:
    return (
        "<header class='top'><div class='wrap'><div class='row'>"
        "<div class='brand'><strong>GHADI</strong>"
        "<span>Multi-sensor hazard detection research</span></div>"
        "<nav><a href='/'>Simulation</a><a href='#methodology'>Methodology</a>"
        "<a href='#references'>References</a>"
        "<span class='chip-badge'>Research prototype</span></nav>"
        "</div></div></header>"
    )


def _notice() -> str:
    return (
        "<div class='notice'><b>Offline research simulation.</b> Results are generated from the "
        "selected scenario and inputs. This interface is not an operational public warning "
        "system, and no data feed is connected.</div>"
    )


def _empty_outcome() -> str:
    return (
        "<div class='panel'><h2 class='sec'>Simulated outcome</h2>"
        "<p class='lede'>Select a scenario or set parameters, then run the simulation to see "
        "the decision, confidence score, evidence, and estimated warning times.</p></div>"
    )


SCRIPT = """
<script>
function copyCap(){var el=document.getElementById('cap');if(!el)return;
navigator.clipboard.writeText(el.textContent).then(function(){});}
(function(){var f=document.getElementById('sim');var s=document.getElementById('stale');
if(f&&s){f.addEventListener('input',function(){s.hidden=false;});}})();
</script>
"""


def _page(q: dict[str, str]) -> str:
    ran = any(k in q for k in PARAM_KEYS)
    inp, errors = _validate(q)
    scenario = _scenario_name(q, ran and not errors)

    if inp is None or not ran:
        left = _form(inp or Inputs(*CASCADE, "surge", True, False, 60.0), errors, scenario)
        right = (
            _empty_outcome()
            if not errors
            else (
                "<div class='panel'><h2 class='sec'>Cannot run</h2>"
                "<p class='lede'>Fix the highlighted parameters and run again.</p></div>"
            )
        )
        body = f"<div class='workspace'><div>{left}</div><div>{right}</div></div>"
        return _shell(body, ran=False)

    o = _run(inp)
    stale = "<div class='stale' id='stale' hidden>Inputs changed. Re-run required.</div>"
    scen_line = (
        f"<p class='lede' style='margin:0 0 10px'>Scenario: <b>{html.escape(scenario)}</b></p>"
    )
    right = (
        stale
        + scen_line
        + _outcome_panel(o)
        + (f"<div class='grid2'>{_confidence(o)}{_channels(o)}</div>")
    )
    left = _form(inp, errors, scenario)
    workspace = f"<div class='workspace'><div>{left}</div><div>{right}</div></div>"
    evidence = (
        "<div class='panel section' id='evidence'><h2 class='sec'>Evidence</h2>"
        "<p class='lede'>Sensor evidence behind the decision. Observed data would be marked "
        "green; every input here is <span class='syn'>synthetic</span>.</p>"
        f"<div class='plots'>{_seismic_evidence(inp, o)}{_gauge_evidence(inp)}</div></div>"
    )
    exports = (
        "<div class='panel section'><h2 class='sec'>Reproducibility</h2>"
        "<p class='lede'>Export a faithful record of this run. Files are labelled as "
        "simulation and test status.</p><div class='controls'>"
        f"<a class='btn' href='/export?{_qs(inp)}&amp;format=json'>Export JSON</a>"
        f"<a class='btn' href='/export?{_qs(inp)}&amp;format=csv'>Export warning times (CSV)</a>"
        "<a class='btn' href='/compare'>Compare scenarios</a></div></div>"
    )
    body = workspace + _warning_chart(o) + evidence + exports + _details(inp, o, ran=True)
    return _shell(body, ran=True)


def _shell(body: str, ran: bool) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>GHADI research dashboard</title><style>"
        + CSS
        + "</style></head><body>"
        + _header()
        + "<main class='wrap'>"
        + _notice()
        + "<div class='title'><h1>Multi-sensor hazard detection simulation</h1>"
        "<p>Explore how seismic and gauge evidence combine into a simulated surge-warning "
        "decision and estimated lead time for a Himalayan river reach.</p></div>"
        + body
        + "</main><footer><div class='wrap'>GHADI research prototype. Offline simulation; "
        "not an operational warning system. Alert payloads remain status=Test, "
        "scope=Restricted.</div></footer>" + (SCRIPT if ran else "") + "</body></html>"
    )


def _compare_page() -> str:
    head = (
        "<tr><td><b>Scenario</b></td><td><b>Outcome</b></td><td><b>Score</b></td>"
        "<td><b>Timure</b></td><td><b>Syabrubesi</b></td><td><b>Bidur</b></td></tr>"
    )
    rows = ""
    for lbl, qs, _ in PRESETS:
        inp, _e = _validate(dict(urllib.parse.parse_qsl(qs)))
        assert inp is not None
        o = _run(inp)
        s = STATE[o.decision.tier.value]
        lt = o.lead_times_min or {}
        cells = "".join(
            f"<td class='tnum'>{lt[n]:.0f} min</td>" if n in lt else "<td>n/a</td>"
            for n in ("Timure", "Syabrubesi", "Bidur")
        )
        rows += (
            f"<tr><td><a href='/?{qs}'>{html.escape(lbl)}</a></td>"
            f"<td style='color:{s['c']};font-weight:600'>{s['label']}</td>"
            f"<td class='tnum'>{o.decision.probability:.2f}</td>{cells}</tr>"
        )
    body = (
        "<div class='panel section'><h2 class='sec'>Scenario comparison</h2>"
        "<p class='lede'>Every preset run under its own inputs. Estimated warning lead time in "
        "minutes (single-event travel model, n=1).</p>"
        f"<table class='kv'>{head}{rows}</table>"
        "<div class='controls' style='margin-top:14px'><a class='btn' href='/'>Back to "
        "simulation</a></div></div>"
    )
    return _shell(body, ran=False)


def _export(q: dict[str, str]) -> tuple[bytes, str, str]:
    inp, _e = _validate(q)
    if inp is None:
        return b'{"error":"invalid parameters"}', "application/json", "ghadi_error.json"
    o = _run(inp)
    fmt = q.get("format", "json")
    if fmt == "cap":
        body = (o.alert_xml or "<!-- no alert emitted -->").encode("utf-8")
        return body, "application/xml", "ghadi_alert.xml"
    if fmt == "csv":
        buf = io.StringIO()
        buf.write("settlement,estimated_lead_time_min,status\n")
        for name, lead in sorted((o.lead_times_min or {}).items(), key=lambda kv: kv[1]):
            buf.write(f"{name},{lead:.0f},simulated\n")
        return buf.getvalue().encode("utf-8"), "text/csv", "ghadi_warning_times.csv"
    payload = {
        "simulation": True,
        "operational": False,
        "reach": REACH_ID,
        "river_system": RIVER_SYSTEM,
        "model_version": MODEL_VERSION,
        "inputs": asdict(inp),
        "input_provenance": "synthetic; n=1 travel calibration",
        "decision": {
            "tier": o.decision.tier.value,
            "fused_score": round(o.decision.probability, 4),
            "warning_threshold": WARNING_P,
            "independent_groups": o.decision.independent_groups,
            "channels_alive": list(o.decision.channels_alive),
            "channels_dead": list(o.decision.channels_dead),
            "rationale": o.decision.rationale,
        },
        "teleseism_suppressed": o.suppression.suppressed,
        "estimated_lead_time_min": o.lead_times_min,
        "alert_status": "Test",
        "alert_scope": "Restricted",
        "generated_utc": datetime.now(UTC).isoformat(),
    }
    return json.dumps(payload, indent=2).encode("utf-8"), "application/json", "ghadi_result.json"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        if parsed.path == "/compare":
            self._send(_compare_page().encode("utf-8"), "text/html; charset=utf-8")
        elif parsed.path == "/export":
            body, ctype, fname = _export(q)
            self._send(body, ctype, {"Content-Disposition": f"attachment; filename={fname}"})
        elif parsed.path in ("/", ""):
            self._send(_page(q).encode("utf-8"), "text/html; charset=utf-8")
        else:
            self.send_response(404)
            self.end_headers()

    def _send(self, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"GHADI dashboard on http://localhost:{PORT}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
