"""Architectural rule 1, enforced by test rather than convention.

The detection path and the analysis path are physically separate services. In a
disaster the analysis path will be down — that is when detection matters most. The
detector must not import anything that can block on a satellite API, or pull in a
plotting stack, or open a network client.

This runs in a clean subprocess because import side effects are global: checking
``sys.modules`` inside the main pytest process would see obspy imported by some other
test and fail for the wrong reason.
"""

from __future__ import annotations

import subprocess
import sys

DETECTION_MODULES = [
    "ghadi.config",
    "ghadi.features",
    "ghadi.detect.sta_lta",
    "ghadi.hydro",
    "ghadi.fusion",
    "ghadi.cap",
]

FORBIDDEN_ON_DETECTION_PATH = [
    "obspy",  # heavy, and its clients block on the network
    "matplotlib",  # plotting belongs to the analysis path
    "urllib.request",
    "http.client",
    "requests",
]

PROBE = """
import sys
for module in {modules!r}:
    __import__(module)
leaked = [name for name in {forbidden!r} if name in sys.modules]
print(",".join(leaked))
"""


def test_detection_path_imports_nothing_heavy_or_networked() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            PROBE.format(modules=DETECTION_MODULES, forbidden=FORBIDDEN_ON_DETECTION_PATH),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    leaked = [name for name in result.stdout.strip().split(",") if name]
    assert not leaked, (
        f"detection path pulled in {leaked} — it must stay import-clean so it survives "
        "when the analysis path is down (docs/ARCHITECTURE.md rule 1)"
    )


def test_fdsn_layer_imports_obspy_lazily() -> None:
    """Importing ghadi.fdsn must not itself drag obspy in; only calling it does.

    This keeps the module importable (for its dataclasses and cache keys) inside a
    lean detection process.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import ghadi.fdsn, sys; print('obspy' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"
