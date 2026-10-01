# Making a citable release

A result that someone else builds on needs two permanent things: a version of the code
and a copy of the data it rests on. This is how to make both. Nothing here is done
automatically, because publishing is the project owner's decision.

## 1. Check that the results regenerate

```bash
python scripts/reproduce.py
```

Every experiment should report `reproduced`, `superseded` with its reason, or
`no script`. Fix anything that says `differs` before going further: a release whose
numbers do not regenerate is not a release.

## 2. Redraw the figures

```bash
python scripts/make_figures.py
```

## 3. Set the version

Change `version` in `pyproject.toml` and in `CITATION.cff` to the same value, and
commit.

## 4. Build the data bundle

```bash
python scripts/make_release_bundle.py
```

This writes `dist/ghadi-data-<version>.tar.gz` and a manifest of every file with its
size and SHA-256 digest, then verifies the bundle against the manifest. The bundle
holds the catalogue, the corpora, the catchment outline, every experiment's findings,
results, and script, and the figures. It does not hold the waveform or imagery caches:
those are other people's data and can be fetched again from their sources. The
manifest names the sources.

## 5. Tag the code

```bash
git tag -a v<version> -m "GHADI <version>"
```

```bash
git push origin v<version>
```

## 6. Deposit and get an identifier

Upload the bundle to a research data archive such as Zenodo, with the licence, the
authors, and a link to the tagged code. The archive gives the deposit a permanent
identifier. Add it to `CITATION.cff` as a `doi` field and to the README, and commit.

If the repository is connected to the archive's GitHub integration, publishing a
GitHub release from the tag deposits the code as well and gives it its own identifier.

## What to say about the data's limits

The deposit description should carry the same limits the README does: one confirmed
event, false alarm rates measured on about a third of a station month per station,
thresholds with a chosen margin, and a gauge channel that has never seen real data.
