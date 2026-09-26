"""The other cost of margin: how many real earthquakes pass the spectral test at each one.

exp005 and exp010 measured the earthquake overlap at zero margin (11 of 64 at NK.KKN,
6 of 132 at IO.EVN). Loosening the thresholds lets more earthquakes through, and that
number belongs next to the false alarm rate. This recomputes the decision segment
features for every earthquake in both corpora from the cache and counts the overlap at
each margin of exp022.

    GHADI_OFFLINE=1 python experiments/exp022_margin_and_joint_rules/earthquake_overlap.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghadi.config import DEFAULT, EVEREST, KAKANI, StationSite  # noqa: E402
from ghadi.fdsn import CachedWaveformClient, WaveformRequest  # noqa: E402
from ghadi.features import extract, preprocess  # noqa: E402

CORPUS = REPO_ROOT / "data" / "corpus"
MARGINS = (0.0, 0.1, 0.2, 0.3, 0.5)
BASE = {"NK.KKN": (4.9188, 1.8852), "IO.EVN": (15.0726, 1.5325)}
FILES = {"NK.KKN": "earthquakes.json", "IO.EVN": "earthquakes_IO_EVN.json"}
SITES: dict[str, StationSite] = {"NK.KKN": KAKANI, "IO.EVN": EVEREST}


def segment_features(
    client: CachedWaveformClient, site: StationSite, row: dict[str, Any]
) -> tuple[float, float] | None:
    start = datetime.fromisoformat(row["window_start_utc"])
    end = datetime.fromisoformat(row["window_end_utc"])
    r = client.get_waveforms(
        WaveformRequest(
            site.site.network, site.site.station, site.site.location, site.site.channel, start, end
        )
    )
    if not r.ok:
        return None
    tr = r.stream.merge(fill_value="interpolate")[0]
    sr = float(tr.stats.sampling_rate)
    proc = preprocess(np.asarray(tr.data, dtype=float), sr)
    try:
        seg = extract(
            proc,
            sr,
            preprocessed=True,
            onset_s=float(row["onset_s"]),
            segment_s=DEFAULT.seismic.decision_segment_s,
        )
    except ValueError:
        return None
    if not (np.isfinite(seg.spectral_ratio_low_high) and np.isfinite(seg.spectral_centroid_hz)):
        return None
    return float(seg.spectral_ratio_low_high), float(seg.spectral_centroid_hz)


def main() -> int:
    client = CachedWaveformClient()
    out: dict[str, Any] = {"margins": list(MARGINS), "stations": {}}
    for key, fname in FILES.items():
        corpus = json.loads((CORPUS / fname).read_text(encoding="utf-8"))
        rows = [
            e for e in corpus["events"] if e.get("status") == "ok" and e.get("onset_s") is not None
        ]
        feats = [f for f in (segment_features(client, SITES[key], r) for r in rows) if f]
        lf0, cen0 = BASE[key]
        by_margin = {}
        for m in MARGINS:
            n = sum(1 for lf, cen in feats if lf >= lf0 * (1 - m) and cen <= cen0 * (1 + m))
            by_margin[str(m)] = {
                "earthquakes_passing": n,
                "of": len(feats),
                "share": round(n / len(feats), 3) if feats else None,
            }
        out["stations"][key] = {"usable": len(feats), "of_rows": len(rows), "by_margin": by_margin}
        print(f"{key}: {len(feats)} earthquakes with segment features (of {len(rows)} rows)")
        for m, rec in by_margin.items():
            print(
                f"   margin {float(m):.1f}: {rec['earthquakes_passing']:3d} of {rec['of']} "
                f"({rec['share']})"
            )
    path = Path(__file__).resolve().parent / "earthquake_overlap.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"results -> {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
