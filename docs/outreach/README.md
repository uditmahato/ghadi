# Outreach letters (issue 0.2)

Three letters gate roughly half the programme, and **none of them is a research
question**. They should go out in week one.

| Letter | To | Blocker | Asks for |
|---|---|---|---|
| [ndrrma.md](ndrrma.md) | NDRRMA | B1 | Does BIPAD expose an API? Access to incident records |
| [dhm.md](dhm.md) | DHM | B2 | Gauge series at native sampling; status of the CAP SOP |
| [dmg-nemrc.md](dmg-nemrc.md) | DMG / NEMRC | B3 | Waveform access, station metadata, collaboration |

## Status

**Drafts only. Nothing has been sent.** Two things must be settled before they go:

1. **Who signs.** Handoff §16 question 5: these are materially more effective over an
   institutional signature than a researcher's. The signatory determines the letterhead,
   the return address, and in practice whether the letter is answered.
2. **Which institution the project belongs to.** Handoff §16 question 2 — NDRRMA, DHM,
   or a university under an MoU. The letters currently avoid claiming an affiliation
   rather than inventing one; that placeholder must be filled before sending.

Placeholders are marked `[LIKE THIS]`.

## What to do with the answers

Record them in [../DATA_SOURCES.md](../DATA_SOURCES.md) against the relevant blocker,
including a refusal. A documented "no" is a planning input; an unanswered letter is not,
and the difference matters when the schedule is being defended.

Each letter's fallback is already designed in, so a refusal delays a feature rather than
stopping the project:

- **B1 refused** → integrate by CAP file drop, treat BIPAD as write-only.
- **B2 refused** → ship the seismic-only detector; fusion is deferred, not cancelled.
- **B3 refused** → archive FDSN access already covers M1–M3; only real-time SeedLink
  is at risk, and the preliminary measurement in [../LATENCY.md](../LATENCY.md)
  suggests the public EarthScope relay may suffice on its own.
