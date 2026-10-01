"""Draw the figures from the committed results.

    python scripts/make_figures.py            # everything it has inputs for
    python scripts/make_figures.py fig02      # one figure by prefix

Every figure is drawn from a ``results.json`` already in the repository, so the picture
and the number cannot drift apart. The one exception is the waveform figure, which
needs the 2026 windows in the local waveform cache and is skipped, with a message,
when they are not there.

Figures are written to ``docs/figures``. The tables in each experiment's FINDINGS are
the table view of the same data.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
EXP = REPO / "experiments"
OUT = REPO / "docs" / "figures"

# Categorical slots, in fixed order, validated on this surface (dataviz validator:
# CVD and normal vision pass; aqua and yellow sit under 3:1 contrast, so every series
# is labelled directly and never identified by colour alone).
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2dd"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": MUTED,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "lines.linewidth": 2.0,
        "lines.markersize": 7,
        "font.family": "DejaVu Sans",
    }
)


def load(name: str) -> dict[str, Any] | None:
    path = EXP / name / "results.json"
    if not path.exists():
        return None
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def save(fig: Any, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote docs/figures/{name}")


def end_label(ax: Any, x: float, y: float, text: str, dy: float = 0.0) -> None:
    ax.annotate(
        text, (x, y), xytext=(6, dy), textcoords="offset points", va="center", color=INK, fontsize=9
    )


# --------------------------------------------------------------------------------------
def fig01_event() -> None:
    """The 2026 event at both stations: the trace and the spectrum of its decision segment."""
    from ghadi.config import DEFAULT, EVEREST, KAKANI
    from ghadi.detect import pick_onset, sta_lta
    from ghadi.fdsn import CachedWaveformClient, WaveformRequest
    from ghadi.features import preprocess
    from ghadi.geo import haversine_km

    origin = datetime(2026, 8, 26, 2, 52, 10, tzinfo=UTC)
    client = CachedWaveformClient()
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.2), gridspec_kw={"width_ratios": [1.7, 1]})
    for row, (site, post) in enumerate(((KAKANI, 2100.0), (EVEREST, 1500.0))):
        start = origin - timedelta(seconds=600)
        r = client.get_waveforms(
            WaveformRequest(
                site.site.network,
                site.site.station,
                site.site.location,
                site.site.channel,
                start,
                origin + timedelta(seconds=post),
            )
        )
        if not r.ok:
            print(f"fig01 skipped: the 2026 window for {site.key} is not in the cache")
            plt.close(fig)
            return
        tr = r.stream.merge(fill_value="interpolate")[0]
        sr = float(tr.stats.sampling_rate)
        proc = preprocess(np.asarray(tr.data, dtype=float), sr)
        det = sta_lta(proc, sr, preprocessed=True)
        dist = haversine_km(site.latitude, site.longitude, 28.255, 85.520)
        pick = pick_onset(det.triggers, origin_offset_s=600.0, distance_km=dist)
        onset = float(pick.onset_s or 600.0)
        t = np.arange(proc.size) / sr - onset
        keep = (t > -120) & (t < 360)
        ax = axes[row, 0]
        ax.plot(t[keep], proc[keep] / np.max(np.abs(proc[keep])), color=BLUE, linewidth=0.7)
        ax.axvline(0, color=INK, linewidth=1)
        ax.axvspan(0, DEFAULT.seismic.decision_segment_s, color=BLUE, alpha=0.08, linewidth=0)
        ax.set_title(f"{site.key}, {dist:.0f} km from the source")
        ax.set_ylabel("ground velocity, scaled")
        ax.set_yticks([])
        ax.annotate(
            "onset",
            (0, 0.97),
            xycoords=("data", "axes fraction"),
            xytext=(-5, 0),
            textcoords="offset points",
            ha="right",
            va="top",
            fontsize=9,
        )
        ax.annotate(
            "shaded: the 120 s decision segment",
            (128, 0.97),
            xycoords=("data", "axes fraction"),
            ha="left",
            va="top",
            color=MUTED,
            fontsize=9,
        )
        if row == 1:
            ax.set_xlabel("seconds from the onset")

        n = round(DEFAULT.seismic.decision_segment_s * sr)
        a = round(onset * sr)
        seg = proc[a : a + n]
        noise = proc[max(a - round(300 * sr), 0) : a - round(60 * sr)][:n]
        ax2 = axes[row, 1]
        for data, colour, label in (
            (noise, ORANGE, "before the onset"),
            (seg, BLUE, "decision segment"),
        ):
            spec = np.abs(np.fft.rfft(data * np.hanning(data.size))) ** 2
            freq = np.fft.rfftfreq(data.size, 1 / sr)
            band = (freq >= 0.5) & (freq <= 20)
            smooth = np.convolve(spec[band], np.ones(25) / 25, mode="same")
            ax2.loglog(freq[band], smooth, color=colour)
            # Label where the curve is still flat, clear of the band edge roll off.
            at = int(np.searchsorted(freq[band], 0.75 * freq[band][-1]))
            dy = 16 if label == "decision segment" else -20
            ax2.annotate(
                label,
                (freq[band][at], smooth[at]),
                xytext=(0, dy),
                textcoords="offset points",
                ha="center",
                fontsize=9,
            )
        ax2.axvline(DEFAULT.seismic.spectral_split_hz, color=MUTED, linewidth=1, linestyle=":")
        ax2.set_title("power spectrum")
        ax2.set_xlim(0.5, 25)
        ax2.set_yticks([])
        if row == 1:
            ax2.set_xlabel("frequency, Hz (dotted line: 3 Hz split)")
    fig.suptitle(
        "The 26 August 2026 event: energy arrives below 3 Hz at both stations",
        x=0.01,
        ha="left",
        fontweight="bold",
    )
    fig.tight_layout()
    save(fig, "fig01_event_2026.png")


def fig02_detection_curve() -> None:
    d = load("exp026_injection_detection_curve")
    if d is None:
        print("fig02 skipped: exp026 has no results yet")
        return
    factors = [f for f in d["factors"] if f > 0]
    s = d["summary"]
    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    series = (
        ("trigger found", BLUE, lambda e: e["margin20"]["trigger"]),
        ("detected, 20% margin", ORANGE, lambda e: e["margin20"]["detected"]),
        ("detected, no margin", AQUA, lambda e: e["margin0"]["detected"]),
    )
    last = []
    for label, colour, get in series:
        y = [get(s[str(f)]) for f in factors]
        ax.plot(factors, y, color=colour, marker="o", markeredgecolor=SURFACE, markeredgewidth=2)
        last.append((label, y[-1], colour))
    offsets = [8, 0, -8]
    for (label, y, _), dy in zip(sorted(last, key=lambda v: -v[1]), offsets, strict=True):
        end_label(ax, factors[-1], y, label, dy)
    ax.set_xscale("log")
    ax.set_xticks(factors)
    ax.set_xticklabels([f"{f:g}" for f in factors])
    ax.set_xlim(factors[0] * 0.8, factors[-1] * 3.2)
    ax.set_ylim(-0.03, 1.05)
    ax.set_xlabel("size of the injected event, as a share of the 2026 amplitude")
    ax.set_ylabel("share of noise windows in which it is caught")
    ax.set_title(f"How small an event is still caught ({d['windows_used']} noise windows, NK.KKN)")
    ctrl = s["0.0"]["margin20"]["detected"]
    ax.annotate(f"with nothing injected: {ctrl:.0%}", (factors[0], 0.1), color=MUTED, fontsize=9)
    save(fig, "fig02_detection_curve.png")


def fig03_ablation() -> None:
    d = load("exp027_ablation")
    if d is None:
        print("fig03 skipped: exp027 has no results")
        return
    labels = [
        "trigger only",
        "+ spectral",
        "+ catalogue",
        "+ H/V",
        "+ partner",
        "all, with fallback",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.9), sharey=True)
    for ax, key in zip(axes, ("NK.KKN", "IO.EVN"), strict=True):
        st = d["stations"][key]
        vals = [b["per_station_month"] for b in st["cumulative"].values()]
        vals.append(st["all_rules_with_fallback_when_partner_missing"]["per_station_month"])
        shown = [max(v, 0.7) for v in vals]
        y = np.arange(len(vals))[::-1]
        colours = [BLUE] * 5 + [ORANGE]
        ax.barh(y, shown, height=0.6, color=colours, edgecolor=SURFACE, linewidth=2)
        for yi, v, sh in zip(y, vals, shown, strict=True):
            text = "0" if v == 0 else (f"{v:.0f}" if v >= 100 else f"{v:.1f}")
            at = 1.25 if v == 0 else sh
            ax.annotate(text, (at, yi), xytext=(5, 0), textcoords="offset points", va="center")
        ax.set_xscale("log")
        ax.set_xlim(0.7, 6000)
        ax.set_yticks(y)
        ax.set_yticklabels(labels)
        ax.axvline(1, color=INK, linewidth=1)
        ax.set_xlabel("per station month, log scale (black line: the goal of 1)")
        ax.set_title(f"{key}: false alarms per station month")
        ax.grid(axis="y", visible=False)
    fig.suptitle("Each rule added in turn (20% margin)", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    save(fig, "fig03_ablation.png")


def fig04_margin() -> None:
    d = load("exp022_margin_and_joint_rules")
    if d is None:
        print("fig04 skipped: exp022 has no results")
        return
    series = (
        ("spectral only", "spectral", BLUE),
        ("+ H/V", "spectral_hv", ORANGE),
        ("+ partner", "spectral_two_station_catchment", AQUA),
        ("+ H/V + partner", "spectral_hv_two_station_catchment", YELLOW),
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, key in zip(axes, ("NK.KKN", "IO.EVN"), strict=True):
        by = d["stations"][key]["by_margin"]
        margins = [float(m) for m in by]
        ends = []
        for label, field, colour in series:
            y = [by[str(m)][field]["per_station_month"] for m in by]
            ax.plot(
                [100 * m for m in margins],
                y,
                color=colour,
                marker="o",
                markeredgecolor=SURFACE,
                markeredgewidth=2,
            )
            ends.append((label, y[-1]))
        ends.sort(key=lambda v: -v[1])
        placed: list[float] = []
        for label, y in ends:
            dy = 0.0
            while any(abs((y + dy) - p) < 0.06 * max(e[1] for e in ends) for p in placed):
                dy -= 0.06 * max(e[1] for e in ends)
            placed.append(y + dy)
            ax.annotate(
                label,
                (100 * margins[-1], y + dy),
                xytext=(6, 0),
                textcoords="offset points",
                va="center",
                fontsize=9,
            )
        ax.set_xlim(-2, 78)
        ax.set_xticks([100 * m for m in margins])
        ax.set_xlabel("margin on the thresholds, percent")
        ax.set_title(f"{key}: false alarms per station month")
    fig.suptitle(
        "What margin costs, with and without the other rules", x=0.01, ha="left", fontweight="bold"
    )
    fig.tight_layout()
    save(fig, "fig04_margin.png")


def fig05_suppression() -> None:
    d = load("exp024_suppression_threshold")
    if d is None:
        print("fig05 skipped: exp024 has no results")
        return
    st = d["stations"]["IO.EVN"]
    names = {
        "A_m55_any": "M5.5 anywhere",
        "C_within_40deg": "+ M5.0 within 40 deg",
        "C_m55_any_or_m50_within_60deg": "+ M5.0 within 60 deg",
        "C_within_80deg": "+ M5.0 within 80 deg (chosen)",
        "C_within_100deg": "+ M5.0 within 100 deg",
        "B_m50_any": "M5.0 anywhere",
    }
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    xs = [100 * st[k]["set_aside_fraction"] for k in names]
    ys = [st[k]["false_alarm_windows_explained"] for k in names]
    ax.plot(xs, ys, color=BLUE, marker="o", markeredgecolor=SURFACE, markeredgewidth=2)
    for (k, label), x, y in zip(names.items(), xs, ys, strict=True):
        chosen = k == "C_within_80deg"
        ax.annotate(
            label,
            (x, y),
            xytext=(8, -12 if y > 2 else 6),
            textcoords="offset points",
            fontsize=9,
            fontweight="bold" if chosen else "normal",
        )
    ax.set_xlabel("share of time the seismic channel is set aside, percent")
    ax.set_ylabel("IO.EVN false alarms explained, of 29")
    ax.set_xlim(2.5, 19)
    ax.set_ylim(-1, 17)
    ax.set_title("Lowering the distant earthquake threshold: what it buys and costs")
    save(fig, "fig05_suppression.png")


def fig06_radar_nulls() -> None:
    d = load("exp015_seasonal_nulls_2026")
    if d is None:
        print("fig06 skipped: exp015 has no results")
        return
    fig, ax = plt.subplots(figsize=(8.2, 3.4))
    rows = []
    for pol in ("vv", "vh"):
        for g in d["polarisations"][pol]["groups"]:
            if len(g["tracks"]) == 3:
                rows.append((pol.upper(), g["summary"]))
    for i, (_pol, s) in enumerate(rows):
        y = len(rows) - 1 - i
        ax.scatter(
            s["null_largest_km2"],
            [y] * s["n_null"],
            color=BLUE,
            s=55,
            edgecolor=SURFACE,
            linewidth=1.5,
            zorder=3,
        )
        ax.scatter(
            [s["event_largest_km2"]],
            [y],
            color=ORANGE,
            s=110,
            marker="D",
            edgecolor=SURFACE,
            linewidth=1.5,
            zorder=4,
        )
        ax.annotate(
            "26 Aug 2026",
            (s["event_largest_km2"], y),
            xytext=(0, 11),
            textcoords="offset points",
            ha="center",
            fontsize=9,
        )
        if i == 0:
            ax.annotate(
                f"{s['n_null']} windows with no event",
                (s["null_median_km2"], y),
                xytext=(0, -16),
                textcoords="offset points",
                ha="center",
                fontsize=9,
                color=MUTED,
            )
    ax.set_xscale("log")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows][::-1])
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.set_xlabel("largest patch where all three satellite tracks agree, square km")
    ax.set_title("Radar change at the 2026 source against the same weeks of 2022 to 2026")
    ax.grid(axis="y", visible=False)
    save(fig, "fig06_radar_nulls.png")


FIGURES = {
    "fig01": fig01_event,
    "fig02": fig02_detection_curve,
    "fig03": fig03_ablation,
    "fig04": fig04_margin,
    "fig05": fig05_suppression,
    "fig06": fig06_radar_nulls,
}


def main(argv: list[str] | None = None) -> int:
    wanted = (argv if argv is not None else sys.argv[1:]) or list(FIGURES)
    for name, draw in FIGURES.items():
        if any(name.startswith(w) or w.startswith(name) for w in wanted):
            draw()
    return 0


if __name__ == "__main__":
    sys.exit(main())
