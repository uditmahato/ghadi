"""Bundle the data behind the results for an archive deposit.

    python scripts/make_release_bundle.py                 # writes dist/ghadi-data-<version>.tar.gz
    python scripts/make_release_bundle.py --check         # verify an existing bundle

A citation needs something permanent to point at. This collects everything the results
rest on that is small enough to keep and is ours to share, with a manifest of sizes and
SHA-256 digests:

* the event catalogue (``data/catalog``),
* the corpora and their data card (``data/corpus``),
* the catchment outline (``data/geo``),
* every experiment's findings, results, and script,
* the figures, the experiment index, the licence, and the citation file.

**Not included, on purpose.** The waveform and imagery caches. They are large, they are
other people's data (the seismic networks and the Copernicus programme), and they can
be fetched again from their sources by ``scripts/reproduce.py --online``. The manifest
records which networks and collections those are.

This script only builds the bundle. Depositing it in an archive and minting an
identifier is a step for the project owner, described in ``docs/RELEASE.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tarfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
INCLUDE_DIRS = ("data/catalog", "data/corpus", "data/geo", "experiments", "docs/figures")
INCLUDE_FILES = (
    "LICENSE",
    "CITATION.cff",
    "README.md",
    "docs/EXPERIMENTS.md",
    "docs/DATA_SOURCES.md",
    "pyproject.toml",
)
SKIP_PARTS = {"__pycache__", "figures_tmp"}
EXTERNAL = [
    {
        "what": "seismic waveforms",
        "source": "EarthScope FDSN web services; networks NK (Kakani) and IO (Everest Pyramid Lab)",
        "how": "python scripts/reproduce.py --online",
    },
    {
        "what": "Sentinel-1 RTC radar and Copernicus GLO-90 elevation",
        "source": "Microsoft Planetary Computer STAC (Copernicus programme data)",
        "how": "python scripts/reproduce.py --online; python scripts/build_catchment.py",
    },
    {
        "what": "global earthquake origins",
        "source": "USGS FDSN event service",
        "how": "cached copies are inside the bundle under experiments/ and data/corpus/",
    },
]


def version() -> str:
    return str(
        tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    )


def collect() -> list[Path]:
    files: list[Path] = []
    for rel in INCLUDE_DIRS:
        base = REPO / rel
        if base.exists():
            files += [
                p
                for p in sorted(base.rglob("*"))
                if p.is_file() and not (set(p.parts) & SKIP_PARTS) and p.suffix != ".pyc"
            ]
    files += [REPO / f for f in INCLUDE_FILES if (REPO / f).exists()]
    return files


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(out_dir: Path) -> Path:
    ver = version()
    files = collect()
    manifest: dict[str, Any] = {
        "name": "ghadi-data",
        "version": ver,
        "built_utc": datetime.now(tz=UTC).isoformat(),
        "licence": "MIT for code and derived results; third party data under its own terms",
        "not_included": EXTERNAL,
        "files": [
            {
                "path": p.relative_to(REPO).as_posix(),
                "bytes": p.stat().st_size,
                "sha256": digest(p),
            }
            for p in files
        ],
    }
    manifest["total_bytes"] = sum(f["bytes"] for f in manifest["files"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"ghadi-data-{ver}.tar.gz"
    root = f"ghadi-data-{ver}"
    with tarfile.open(out, "w:gz") as tar:
        body = json.dumps(manifest, indent=1).encode("utf-8")
        info = tarfile.TarInfo(f"{root}/MANIFEST.json")
        info.size = len(body)
        tar.addfile(info, io.BytesIO(body))
        for p in files:
            tar.add(p, arcname=f"{root}/{p.relative_to(REPO).as_posix()}")
    (out_dir / f"ghadi-data-{ver}.manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8"
    )
    print(f"{len(files)} files, {manifest['total_bytes'] / 1e6:.1f} MB before compression")
    print(f"wrote {out.relative_to(REPO)} ({out.stat().st_size / 1e6:.1f} MB)")
    print(f"sha256 {digest(out)}")
    return out


def check(bundle: Path) -> int:
    bad = 0
    with tarfile.open(bundle, "r:gz") as tar:
        names = tar.getnames()
        root = names[0].split("/")[0]
        manifest = json.loads(tar.extractfile(f"{root}/MANIFEST.json").read())  # type: ignore[union-attr]
        for entry in manifest["files"]:
            member = tar.extractfile(f"{root}/{entry['path']}")
            if member is None or hashlib.sha256(member.read()).hexdigest() != entry["sha256"]:
                print(f"MISMATCH {entry['path']}")
                bad += 1
    print(f"{len(manifest['files'])} files checked, {bad} mismatched")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out-dir", type=Path, default=REPO / "dist")
    parser.add_argument("--check", type=Path, default=None, help="verify a bundle and exit")
    args = parser.parse_args(argv)
    if args.check:
        return check(args.check)
    bundle = build(args.out_dir)
    return check(bundle)


if __name__ == "__main__":
    sys.exit(main())
