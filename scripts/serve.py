"""Local research dashboard for the GHADI pipeline.

Standard library only, fully offline. A window is run through
``ghadi.service.process_window`` and presented as a light scientific dashboard:
scenario settings on the left, the simulated decision and its evidence on the right,
with seismic and gauge time-series, a warning-time chart, provenance, and methodology.

    python scripts/serve.py          # then open http://localhost:8770

This is a research prototype running an offline simulation. The live SeedLink/DHM feed
(issue 0.1) is not wired, so nothing here is a live alert; every payload stays
status=Test, scope=Restricted.
"""

from __future__ import annotations

import html
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
DETECTED = datetime(2026, 8, 26, 2, 52, 24, tzinfo=UTC)
CASCADE = (4.9188, 1.8852)
MAX_LEAD_MIN = 40.0
RATE_THRESHOLD = DEFAULT.hydro.rate_threshold_m_per_min
MODEL_VERSION = "sta_lta@v0.1.0 + classify@v0.1.0 + fusion@v0.1.0"
REACH_ID = "TRISHULI-R07"
RIVER_SYSTEM = "Lhende Khola to Bhote Koshi to Trishuli"

# Result-state colours. Red/amber/green are reserved for these states only.
STATE = {
    "WARNING": {"c": "#B3372B", "bg": "#FCEDEC", "bd": "#E4B7B2", "label": "Warning"},
    "ADVISORY": {"c": "#B9770E", "bg": "#FBF4E7", "bd": "#E7D5AB", "label": "Advisory"},
    "WATCH": {"c": "#256A91", "bg": "#EAF2F8", "bd": "#C2D8E7", "label": "Watch"},
    "NONE": {"c": "#5E6C84", "bg": "#F1F3F7", "bd": "#DFE4EC", "label": "No alert"},
}
STATE_MEANING = {
    "WARNING": "Two independent lines of evidence agree on a surge threat.",
    "ADVISORY": "One line of evidence indicates a possible surge. Confirm before acting.",
    "WATCH": "A weak or single signal is present. Keep monitoring.",
    "NONE": "No evidence crossed the decision threshold.",
}
SAMPLE_INSTRUCTION = {
    "WARNING": "Move away from the river channel to higher ground immediately.",
    "ADVISORY": "Prepare to move away from the river channel. Await confirmation.",
    "WATCH": "Monitor official channels. No action required at this time.",
    "NONE": "Monitor official channels. No action required at this time.",
}
LEAD_GREEN, LEAD_AMBER, LEAD_RED = "#2E7D5B", "#B9770E", "#B3372B"

PRESETS = [
    ("2026 cascade", "lf_hf=4.9188&centroid=1.8852&gauge=surge&station=on", "the real event"),
    ("Earthquake + surge", "lf_hf=1.66&centroid=3.04&gauge=surge&station=on", "gauge carries it"),
    ("Teleseism", "lf_hf=4.9188&centroid=1.8852&gauge=none&teleseism=on", "distant quake"),
    ("Dead gauge", "lf_hf=1.66&centroid=3.04&gauge=dead", "sensor died"),
    ("Quiet day", "lf_hf=1.66&centroid=3.04&gauge=quiet", "nothing happening"),
    ("Slow pipeline", "lf_hf=4.9188&centroid=1.8852&gauge=surge&latency=600", "loses the race"),
]

CSS = """
:root {
  --bg:#F7F9FC; --panel:#FFFFFF; --ink:#172B4D; --muted:#5E6C84;
  --line:#DFE4EC; --accent:#256A91; --accent-soft:#EAF2F8;
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.6 "Segoe UI", system-ui, -apple-system, Roboto, Helvetica, Arial, sans-serif; }
a { color:var(--accent); }
.wrap { max-width:1240px; margin:0 auto; padding:28px 32px 64px; }
header.top { display:flex; align-items:flex-start; justify-content:space-between;
  gap:24px; flex-wrap:wrap; border-bottom:1px solid var(--line); padding-bottom:18px; }
.brand h1 { margin:0; font-size:1.9rem; font-weight:700; letter-spacing:-.01em; }
.brand p { margin:.15rem 0 0; color:var(--muted); font-size:1rem; }
nav { display:flex; gap:18px; margin-top:12px; font-size:.95rem; }
nav a { text-decoration:none; color:var(--muted); }
nav a:hover, nav a.active { color:var(--accent); }
.badge { display:inline-flex; align-items:center; gap:8px; font-size:.82rem;
  color:var(--accent); background:var(--accent-soft); border:1px solid #C2D8E7;
  border-radius:999px; padding:6px 12px; white-space:nowrap; }
.badge .dot { width:8px; height:8px; border-radius:50%; background:var(--accent); }
.layout { display:grid; grid-template-columns:340px 1fr; gap:24px; margin-top:24px; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:20px; }
.panel h2 { margin:0 0 4px; font-size:1.1rem; font-weight:600; }
.panel .lede { margin:0 0 16px; color:var(--muted); font-size:.9rem; }
.field { margin-bottom:14px; }
.field label { display:block; font-size:.9rem; color:var(--ink); margin-bottom:5px; }
.field .help { font-size:.8rem; color:var(--muted); margin-top:4px; }
input, select { width:100%; font:inherit; font-size:.95rem; padding:8px 10px;
  border:1px solid var(--line); border-radius:7px; background:#FCFDFE; color:var(--ink); }
input:focus, select:focus { outline:2px solid var(--accent-soft); border-color:var(--accent); }
.check { display:flex; align-items:center; gap:9px; font-size:.95rem; margin-bottom:12px; }
.check input { width:auto; }
.btn { display:inline-block; font:inherit; font-size:.95rem; padding:9px 14px;
  border-radius:8px; border:1px solid var(--line); background:#fff; color:var(--ink);
  cursor:pointer; text-decoration:none; }
.btn.primary { background:var(--accent); border-color:var(--accent); color:#fff;
  width:100%; font-weight:600; padding:11px; }
.btn.primary:hover { background:#1f5c7e; }
.presets { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }
.chip { text-decoration:none; color:var(--ink); background:#fff; border:1px solid var(--line);
  border-radius:8px; padding:7px 11px; font-size:.86rem; }
.chip:hover { border-color:var(--accent); }
.chip small { color:var(--muted); }
.actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:14px; }
.result { border-radius:10px; padding:20px 22px; }
.result .tag { font-size:.82rem; letter-spacing:.06em; text-transform:uppercase;
  font-weight:600; }
.result h2 { margin:.2rem 0 .3rem; font-size:1.5rem; }
.result .mean { margin:0; font-size:1rem; }
.cards { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:18px; }
.metric { background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:16px; }
.metric .t { font-size:.9rem; color:var(--muted); margin-bottom:8px; }
.metric .v { font-size:1.7rem; font-weight:700; font-variant-numeric:tabular-nums; }
.metric .u { font-size:.9rem; color:var(--muted); font-weight:400; }
.pill { display:inline-block; padding:4px 10px; border-radius:999px; font-size:.85rem;
  font-weight:600; margin:3px 5px 3px 0; }
.pill.on { background:#E7F3EC; color:#2E7D5B; }
.pill.off { background:#FBECEA; color:#B3372B; }
.note { font-size:.88rem; color:var(--muted); margin-top:10px; }
.section { background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:22px; margin-top:24px; }
.section h2 { margin:0 0 4px; font-size:1.15rem; }
.section .lede { color:var(--muted); font-size:.9rem; margin:0 0 18px; }
.plots { display:grid; grid-template-columns:1fr 1fr; gap:22px; }
.plot h3 { font-size:.98rem; margin:0 0 2px; font-weight:600; }
.plot .cap { font-size:.82rem; color:var(--muted); margin:0 0 8px; }
svg { width:100%; height:auto; display:block; }
.leadchart .row { display:grid; grid-template-columns:120px 1fr 78px; align-items:center;
  gap:12px; margin:8px 0; }
.leadchart .bar { height:20px; background:#EEF1F6; border-radius:5px; position:relative; }
.leadchart .bar > span { display:block; height:100%; border-radius:5px; }
.leadchart .val { text-align:right; font-variant-numeric:tabular-nums; font-weight:600;
  font-size:.92rem; }
.scale { display:grid; grid-template-columns:120px 1fr 78px; gap:12px;
  color:var(--muted); font-size:.78rem; margin-top:4px; }
.scale .ticks { display:flex; justify-content:space-between; }
.legend { display:flex; gap:16px; flex-wrap:wrap; font-size:.82rem; color:var(--muted);
  margin-top:12px; }
.legend span b { display:inline-block; width:10px; height:10px; border-radius:2px;
  margin-right:5px; }
table.kv { border-collapse:collapse; width:100%; font-size:.9rem; }
table.kv td { border-bottom:1px solid var(--line); padding:8px 6px; vertical-align:top; }
table.kv td:first-child { color:var(--muted); width:38%; }
details.method { border:1px solid var(--line); border-radius:8px; padding:2px 16px;
  margin-bottom:10px; background:#FCFDFE; }
details.method > summary { cursor:pointer; font-weight:600; padding:12px 0; font-size:.98rem; }
details.method p, details.method li { font-size:.9rem; color:#2C3A55; }
pre { background:#0f1b2d; color:#d7e3f4; padding:14px; border-radius:8px; overflow-x:auto;
  font-size:.8rem; line-height:1.5; }
.obs { color:#2E7D5B; font-weight:600; } .syn { color:#B9770E; font-weight:600; }
@media (max-width:920px) { .layout, .cards, .plots { grid-template-columns:1fr; } }
"""


@dataclass
class Inputs:
    lf_hf: float
    centroid: float
    gauge: str
    station_alive: bool
    teleseism: bool
    latency: float
    scenario: str = "Custom"


def _parse(q: dict[str, str]) -> Inputs:
    touched = bool(q)
    scenario = "Custom"
    qs_now = urllib.parse.urlencode(
        {
            k: q[k]
            for k in q
            if k in ("lf_hf", "centroid", "gauge", "station", "teleseism", "latency")
        }
    )
    for label, preset_qs, _ in PRESETS:
        if _same_query(preset_qs, qs_now):
            scenario = label
    if not touched:
        scenario = "2026 cascade"
    return Inputs(
        lf_hf=float(q.get("lf_hf", CASCADE[0])),
        centroid=float(q.get("centroid", CASCADE[1])),
        gauge=q.get("gauge", "surge"),
        station_alive=(q.get("station", "on") == "on") if touched else True,
        teleseism=q.get("teleseism", "") == "on",
        latency=float(q.get("latency", 60.0)),
        scenario=scenario,
    )


def _same_query(a: str, b: str) -> bool:
    da = dict(urllib.parse.parse_qsl(a))
    db = dict(urllib.parse.parse_qsl(b))
    keys = {"lf_hf", "centroid", "gauge", "station", "teleseism", "latency"}
    return {k: da.get(k) for k in keys} == {k: db.get(k) for k in keys}


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
                time_utc=DETECTED,
                latitude=PRIMARY_STATION_LAT,
                longitude=PRIMARY_STATION_LON,
                magnitude=6.5,
                place="injected distant earthquake",
            ),
        )
    obs = WindowObservation(
        window_start_utc=DETECTED - timedelta(seconds=120),
        detected_utc=DETECTED,
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


# --------------------------------------------------------------------------------------
# SVG line chart
# --------------------------------------------------------------------------------------
def _ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    return [lo + (hi - lo) * i / n for i in range(n + 1)]


def _svg_line(
    xs,  # type: ignore[no-untyped-def]
    ys,
    xlabel: str,
    ylabel: str,
    color: str,
    threshold: float | None = None,
    threshold_label: str = "",
    vline: float | None = None,
    vline_label: str = "",
    yfmt: str = "{:.1f}",
) -> str:
    w, h = 560, 220
    pl, pr, pt, pb = 54, 14, 14, 40
    xlo, xhi = float(min(xs)), float(max(xs))
    ylo = min(0.0, float(min(ys)))
    yhi = float(max(ys))
    if threshold is not None:
        yhi = max(yhi, threshold)
    if yhi <= ylo:
        yhi = ylo + 1

    def px(x: float) -> float:
        return pl + (x - xlo) / (xhi - xlo) * (w - pl - pr)

    def py(y: float) -> float:
        return h - pb - (y - ylo) / (yhi - ylo) * (h - pt - pb)

    parts = [f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='{html.escape(ylabel)}'>"]
    # gridlines + y ticks
    for yt in _ticks(ylo, yhi):
        y = py(yt)
        parts.append(
            f"<line x1='{pl}' y1='{y:.1f}' x2='{w - pr}' y2='{y:.1f}' "
            f"stroke='#EEF1F6' stroke-width='1'/>"
        )
        parts.append(
            f"<text x='{pl - 8}' y='{y + 4:.1f}' text-anchor='end' font-size='11' "
            f"fill='#5E6C84'>{yfmt.format(yt)}</text>"
        )
    # x ticks
    for xt in _ticks(xlo, xhi):
        x = px(xt)
        parts.append(
            f"<text x='{x:.1f}' y='{h - pb + 18}' text-anchor='middle' font-size='11' "
            f"fill='#5E6C84'>{xt:.0f}</text>"
        )
    # axes
    parts.append(
        f"<line x1='{pl}' y1='{pt}' x2='{pl}' y2='{h - pb}' stroke='#B7C1D1' stroke-width='1'/>"
    )
    parts.append(
        f"<line x1='{pl}' y1='{h - pb}' x2='{w - pr}' y2='{h - pb}' stroke='#B7C1D1' "
        f"stroke-width='1'/>"
    )
    # threshold
    if threshold is not None:
        yt = py(threshold)
        parts.append(
            f"<line x1='{pl}' y1='{yt:.1f}' x2='{w - pr}' y2='{yt:.1f}' stroke='#B3372B' "
            f"stroke-width='1.3' stroke-dasharray='5 4'/>"
        )
        parts.append(
            f"<text x='{w - pr}' y='{yt - 5:.1f}' text-anchor='end' font-size='11' "
            f"fill='#B3372B'>{html.escape(threshold_label)}</text>"
        )
    # vline
    if vline is not None and xlo <= vline <= xhi:
        xv = px(vline)
        parts.append(
            f"<line x1='{xv:.1f}' y1='{pt}' x2='{xv:.1f}' y2='{h - pb}' stroke='#256A91' "
            f"stroke-width='1.2' stroke-dasharray='4 3'/>"
        )
        parts.append(
            f"<text x='{xv + 4:.1f}' y='{pt + 12}' font-size='11' fill='#256A91'>"
            f"{html.escape(vline_label)}</text>"
        )
    # polyline
    pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys, strict=True))
    parts.append(f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='1.6'/>")
    # axis labels
    parts.append(
        f"<text x='{(w + pl) / 2:.0f}' y='{h - 4}' text-anchor='middle' font-size='11.5' "
        f"fill='#172B4D'>{html.escape(xlabel)}</text>"
    )
    parts.append(
        f"<text transform='translate(14,{(h - pb + pt) / 2:.0f}) rotate(-90)' "
        f"text-anchor='middle' font-size='11.5' fill='#172B4D'>{html.escape(ylabel)}</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _seismic_trace(lf_hf: float, centroid: float):  # type: ignore[no-untyped-def]
    """Illustrative synthetic velocity trace. The detector uses the spectral features,
    not this trace; it is drawn only to make the source character visible."""
    rng = np.random.default_rng(1)
    t = np.linspace(0.0, 120.0, 600)
    onset = 30.0
    env = np.clip((t - onset) / 12.0, 0, None) * np.exp(-(np.clip(t - onset, 0, None)) / 45.0)
    low = np.sin(2 * np.pi * max(0.6, centroid) * t)
    high = 0.35 * np.sin(2 * np.pi * (centroid + 2.5) * t) / max(1.0, lf_hf)
    amp = env * (low + high) + 0.06 * rng.standard_normal(t.size)
    return t, amp


# --------------------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------------------
def _result_panel(o) -> str:  # type: ignore[no-untyped-def]
    tier = o.decision.tier.value
    s = STATE[tier]
    instr = SAMPLE_INSTRUCTION[tier]
    return (
        f"<div class='result' style='background:{s['bg']};border:1px solid {s['bd']};"
        f"border-left:5px solid {s['c']}'>"
        f"<div class='tag' style='color:{s['c']}'>Simulated outcome</div>"
        f"<h2 style='color:{s['c']}'>{s['label']}</h2>"
        f"<p class='mean'>{html.escape(STATE_MEANING[tier])}</p>"
        f"<div class='note'><b>Sample alert text</b> (illustrative, not a live instruction): "
        f"&ldquo;{html.escape(instr)}&rdquo;</div></div>"
    )


def _metrics(inp: Inputs, o) -> str:  # type: ignore[no-untyped-def]
    p = o.decision.probability
    pills = "".join(
        f"<span class='pill on'>{html.escape(c)}</span>" for c in o.decision.channels_alive
    )
    pills += "".join(
        f"<span class='pill off'>{html.escape(c)} (offline)</span>"
        for c in o.decision.channels_dead
    )
    pills = pills or "<span class='pill off'>no live channel</span>"
    supp = ""
    if o.suppression.suppressed:
        supp = (
            f"<div class='note'>Seismic channel set aside: {html.escape(o.suppression.reason)}"
            f"</div>"
        )
    conf_help = (
        "Combined by noisy-OR across independent evidence groups. These are "
        "<b>assumed operating points, not calibrated to data</b> (one confirmed event, "
        "n=1), so read it as a decision score rather than a validated probability."
    )
    return (
        f"<div class='cards'>"
        f"<div class='metric'><div class='t'>Fused confidence</div>"
        f"<div class='v'>{p:.2f}</div>"
        f"<div class='note'>{html.escape(o.decision.rationale)}</div>"
        f"<div class='note'>{conf_help}</div></div>"
        f"<div class='metric'><div class='t'>Evidence channels</div><div>{pills}</div>"
        f"{supp}<div class='note'>A channel is live if it is reporting; a detection stands "
        f"even if its sensor later fails.</div></div></div>"
    )


def _evidence(inp: Inputs, o) -> str:  # type: ignore[no-untyped-def]
    # Seismic (illustrative).
    st, sa = _seismic_trace(inp.lf_hf, inp.centroid)
    seismic_svg = _svg_line(
        st.tolist(),
        sa.tolist(),
        "Time since window start (s)",
        "Velocity (illustrative)",
        color="#256A91",
        vline=30.0,
        vline_label="onset",
        yfmt="{:.1f}",
    )
    seis_status = "online" if inp.station_alive or o.decision else "offline"
    seismic = (
        f"<div class='plot'><h3>Seismic station NK.KKN "
        f"<span class='syn'>synthetic</span></h3>"
        f"<p class='cap'>Illustrative trace. The classifier decides on spectral features "
        f"over the 120 s segment: LF/HF = {inp.lf_hf:.2f} (threshold 4.92), centroid = "
        f"{inp.centroid:.2f} Hz (threshold 1.89). Station is {html.escape(seis_status)}.</p>"
        f"{seismic_svg}</div>"
    )
    # Gauge (synthetic series the detector actually uses).
    arr = _gauge_arrays(inp.gauge)
    if arr is None:
        gauge = (
            "<div class='plot'><h3>Downstream gauge</h3>"
            "<p class='cap'>No gauge channel in this scenario.</p></div>"
        )
    else:
        times, stage, alive = arr
        rate = rate_of_rise(times, stage, DEFAULT.hydro.rate_window_s)
        anomaly = detect_anomaly(times, stage)
        vmin = (anomaly.time_s / 60.0) if anomaly.time_s is not None else None
        gauge_svg = _svg_line(
            (times / 60.0).tolist(),
            rate.tolist(),
            "Time since window start (min)",
            "Rate of rise (m/min)",
            color="#2E7D5B",
            threshold=RATE_THRESHOLD,
            threshold_label=f"threshold {RATE_THRESHOLD:.2f} m/min",
            vline=vmin,
            vline_label="detected",
            yfmt="{:.2f}",
        )
        peak = float(stage.max() - stage.min())
        life = "sensor survived" if alive else "sensor destroyed mid-event"
        gauge = (
            f"<div class='plot'><h3>Downstream gauge, Timure "
            f"<span class='syn'>synthetic</span></h3>"
            f"<p class='cap'>Rate of rise over time. Peak stage change {peak:.1f} m; "
            f"{html.escape(life)}. Anomaly fires when the rate crosses "
            f"{RATE_THRESHOLD:.2f} m/min.</p>{gauge_svg}</div>"
        )
    return (
        "<div class='section' id='evidence'><h2>Evidence behind the decision</h2>"
        "<p class='lede'>Aligned sensor time-series. Observed data would appear in green; "
        "every series here is <span class='syn'>synthetic</span> because this is a "
        "simulation.</p>"
        f"<div class='plots'>{seismic}{gauge}</div></div>"
    )


def _warning_chart(o) -> str:  # type: ignore[no-untyped-def]
    if not o.lead_times_min:
        return ""
    rows = ""
    for name, lead in sorted(o.lead_times_min.items(), key=lambda kv: kv[1]):
        if lead <= 0:
            color, width, val = LEAD_RED, 4, f"{lead:.0f} min"
        elif lead >= 10:
            color, width, val = LEAD_GREEN, min(100, lead / MAX_LEAD_MIN * 100), f"{lead:.0f} min"
        else:
            color, width, val = LEAD_AMBER, min(100, lead / MAX_LEAD_MIN * 100), f"{lead:.0f} min"
        rows += (
            f"<div class='row'><div>{html.escape(name)}</div>"
            f"<div class='bar'><span style='width:{width}%;background:{color}'></span></div>"
            f"<div class='val'>{val}</div></div>"
        )
    ticks = "".join(f"<span>{t}</span>" for t in (0, 10, 20, 30, 40))
    return (
        "<div class='section' id='warning'><h2>Warning time by settlement</h2>"
        "<p class='lede'>Minutes between an issued alert and the surge arrival, on a shared "
        "0 to 40 minute scale. Estimates from a single-event travel-time model (n=1); the "
        "arrival times are calibrated on the 26 August 2026 event, not a hydraulic "
        "model.</p>"
        f"<div class='leadchart'>{rows}"
        f"<div class='scale'><div></div><div class='ticks'>{ticks}</div>"
        f"<div style='text-align:right'>min</div></div></div>"
        "<div class='legend'>"
        f"<span><b style='background:{LEAD_GREEN}'></b>10 min or more (evacuation plausible)</span>"
        f"<span><b style='background:{LEAD_AMBER}'></b>under 10 min (limited)</span>"
        f"<span><b style='background:{LEAD_RED}'></b>alert arrives after the water</span>"
        "</div></div>"
    )


def _provenance(inp: Inputs) -> str:
    gauge_desc = {
        "surge": "synthetic surge (Trishuli reference, 9 m in 30 min)",
        "quiet": "synthetic quiet river",
        "dead": "synthetic surge, sensor destroyed at 300 s",
        "none": "no gauge channel",
    }[inp.gauge]
    return (
        "<div class='section' id='repro'><h2>Reproducibility</h2>"
        "<p class='lede'>Everything needed to reproduce this run.</p>"
        "<table class='kv'>"
        f"<tr><td>Scenario</td><td>{html.escape(inp.scenario)}</td></tr>"
        f"<tr><td>River reach</td><td>{REACH_ID} ({html.escape(RIVER_SYSTEM)})</td></tr>"
        f"<tr><td>Model version</td><td>{html.escape(MODEL_VERSION)}</td></tr>"
        f"<tr><td>Seismic input</td><td><span class='syn'>synthetic</span> features: "
        f"LF/HF {inp.lf_hf:.2f}, centroid {inp.centroid:.2f} Hz, "
        f"station {'online' if inp.station_alive else 'offline'}</td></tr>"
        f"<tr><td>Gauge input</td><td><span class='syn'>{html.escape(gauge_desc)}</span></td></tr>"
        f"<tr><td>Teleseism catalogue</td><td>{'1 injected M6.5' if inp.teleseism else 'none'}"
        f"</td></tr>"
        f"<tr><td>Warning latency</td><td>{inp.latency:.0f} s</td></tr>"
        f"<tr><td>Travel-time calibration</td><td>26 Aug 2026 event only (n=1)</td></tr>"
        "</table>"
        "<div class='actions'>"
        "<a class='btn' href='/'>Reset parameters</a>"
        "<a class='btn' href='/compare'>Compare scenarios</a>"
        f"<a class='btn' href='/export?{_qs(inp)}'>Export results (JSON)</a>"
        "</div></div>"
    )


def _methodology(inp: Inputs, o) -> str:  # type: ignore[no-untyped-def]
    alert = html.escape(o.alert_xml) if o.alert_xml else "No alert emitted for this outcome."
    return (
        "<div class='section' id='methodology'><h2>Methodology</h2>"
        "<p class='lede'>The reasoning and its limits, kept beside the result.</p>"
        "<details class='method'><summary>Decision logic</summary>"
        "<p>The seismic classifier flags a window as mass-movement-like only when the "
        "low/high spectral ratio is high <b>and</b> the spectral centroid is low (a slow, "
        "low-frequency source). A distant earthquake whose catalogued arrival explains the "
        "onset is set aside. The gauge fires on rate of rise. Live channels are fused by "
        "noisy-OR across independent groups; a Warning needs at least two independent "
        "groups above threshold.</p></details>"
        "<details class='method'><summary>Data sources</summary>"
        "<p>Seismic waveforms would come from open FDSN stations (NK.KKN, IO.EVN). Gauge "
        "data would come from Nepal's DHM under a data-sharing agreement that is not yet in "
        "place. In this simulation both are synthetic.</p></details>"
        "<details class='method'><summary>Assumptions and limitations</summary>"
        "<ul><li>Positive class is a single event (n=1); confidence values are assumed "
        "operating points, not calibrated.</li>"
        "<li>Spectral overlap with real earthquakes is about 17% at this operating point.</li>"
        "<li>Travel times are a single-event fit, not a hydraulic model.</li>"
        "<li>The live SeedLink feed is not wired (issue 0.1), so this is not operational.</li>"
        "</ul></details>"
        f"<details class='method'><summary>Alert payload (CAP 1.2)</summary><pre>{alert}</pre>"
        "</details></div>"
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


def _form(inp: Inputs) -> str:
    def opt(val: str, text: str) -> str:
        sel = "selected" if inp.gauge == val else ""
        return f"<option value='{val}' {sel}>{text}</option>"

    presets = "".join(
        f"<a class='chip' href='/?{qs}'>{html.escape(lbl)} <small>({html.escape(hint)})</small></a>"
        for lbl, qs, hint in PRESETS
    )
    st = "checked" if inp.station_alive else ""
    ts = "checked" if inp.teleseism else ""
    return (
        "<div class='panel'><h2>Scenario</h2>"
        "<p class='lede'>Choose a preset or set the inputs by hand.</p>"
        f"<div class='presets'>{presets}</div>"
        "<form method='get'>"
        "<div class='field'><label>Seismic LF/HF ratio</label>"
        f"<input name='lf_hf' value='{inp.lf_hf}'>"
        "<div class='help'>Low over high frequency energy. Higher means a slower source."
        "</div></div>"
        "<div class='field'><label>Seismic centroid (Hz)</label>"
        f"<input name='centroid' value='{inp.centroid}'>"
        "<div class='help'>Average frequency. Lower means a slower, mass-movement-like source."
        "</div></div>"
        "<div class='field'><label>Downstream gauge</label>"
        f"<select name='gauge'>{opt('surge', 'Surge (real flood)')}{opt('quiet', 'Quiet river')}"
        f"{opt('dead', 'Sensor destroyed')}{opt('none', 'No gauge')}</select></div>"
        "<div class='field'><label>Warning latency (seconds)</label>"
        f"<input name='latency' type='number' value='{inp.latency:.0f}'>"
        "<div class='help'>Time from initiation to an issued alert.</div></div>"
        f"<label class='check'><input type='checkbox' name='station' {st}> "
        "Seismic station online</label>"
        f"<label class='check'><input type='checkbox' name='teleseism' {ts}> "
        "Inject a distant M6.5 earthquake</label>"
        "<button class='btn primary' type='submit'>Run simulation</button>"
        "</form></div>"
    )


def _header(active: str = "Simulation") -> str:
    def link(name: str, href: str) -> str:
        cls = "active" if name == active else ""
        return f"<a class='{cls}' href='{href}'>{name}</a>"

    nav = (
        link("Overview", "/#overview")
        + link("Simulation", "/")
        + link("Methodology", "/#methodology")
        + link("References", "/#repro")
    )
    return (
        "<header class='top'><div class='brand'>"
        "<h1>GHADI</h1>"
        "<p>Multi-sensor hazard detection and warning research.</p>"
        f"<nav>{nav}</nav></div>"
        "<div class='badge'><span class='dot'></span>Research prototype "
        "&middot; Offline simulation</div></header>"
    )


def _shell(body: str, active: str = "Simulation") -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>GHADI research dashboard</title><style>" + CSS + "</style></head><body>"
        "<div class='wrap'>" + _header(active) + body + "</div></body></html>"
    )


def _page(q: dict[str, str]) -> str:
    inp = _parse(q)
    o = _run(inp)
    right = _result_panel(o) + _metrics(inp, o)
    body = (
        f"<div class='layout'><div>{_form(inp)}</div><div>{right}</div></div>"
        + _warning_chart(o)
        + _evidence(inp, o)
        + _provenance(inp)
        + _methodology(inp, o)
    )
    return _shell(body)


def _compare_page() -> str:
    head = (
        "<tr><td><b>Scenario</b></td><td><b>Outcome</b></td><td><b>Confidence</b></td>"
        "<td><b>Timure</b></td><td><b>Syabrubesi</b></td><td><b>Bidur</b></td></tr>"
    )
    rows = ""
    for lbl, qs, _ in PRESETS:
        inp = _parse(dict(urllib.parse.parse_qsl(qs)))
        o = _run(inp)
        s = STATE[o.decision.tier.value]
        lt = o.lead_times_min or {}
        cells = "".join(
            f"<td>{lt[n]:.0f} min</td>" if n in lt else "<td>n/a</td>"
            for n in ("Timure", "Syabrubesi", "Bidur")
        )
        rows += (
            f"<tr><td><a href='/?{qs}'>{html.escape(lbl)}</a></td>"
            f"<td style='color:{s['c']};font-weight:600'>{s['label']}</td>"
            f"<td>{o.decision.probability:.2f}</td>{cells}</tr>"
        )
    body = (
        "<div class='section'><h2>Compare scenarios</h2>"
        "<p class='lede'>Every preset run under identical settings. Minutes of warning at "
        "each settlement (n=1 travel model).</p>"
        f"<table class='kv'>{head}{rows}</table>"
        "<div class='actions'><a class='btn' href='/'>Back to simulation</a></div></div>"
    )
    return _shell(body)


def _export(q: dict[str, str]) -> bytes:
    inp = _parse(q)
    o = _run(inp)
    payload = {
        "scenario": inp.scenario,
        "reach": REACH_ID,
        "river_system": RIVER_SYSTEM,
        "model_version": MODEL_VERSION,
        "inputs": asdict(inp),
        "note": "Research prototype, offline simulation. Inputs are synthetic; n=1 calibration.",
        "decision": {
            "tier": o.decision.tier.value,
            "probability": round(o.decision.probability, 4),
            "channels_alive": list(o.decision.channels_alive),
            "channels_dead": list(o.decision.channels_dead),
            "rationale": o.decision.rationale,
        },
        "teleseism_suppressed": o.suppression.suppressed,
        "lead_times_min": o.lead_times_min,
    }
    return json.dumps(payload, indent=2).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        if parsed.path == "/compare":
            self._send(_compare_page().encode("utf-8"), "text/html; charset=utf-8")
        elif parsed.path == "/export":
            self._send(
                _export(q),
                "application/json",
                extra={"Content-Disposition": "attachment; filename=ghadi_result.json"},
            )
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
