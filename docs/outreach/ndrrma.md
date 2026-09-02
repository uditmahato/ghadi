# Letter — NDRRMA

**To:** Chief Executive, National Disaster Risk Reduction and Management Authority
**From:** [SIGNATORY, INSTITUTION]
**Subject:** Data access request — BIPAD portal interface and incident records
**Status:** DRAFT — not sent

---

Dear [NAME],

We are developing a detection system for cascading flood surges in transboundary
Himalayan rivers, prompted by the 26 August 2026 Bhote Koshi event. The system listens
to continuous seismic waveforms from Nepal's own NK network for the signature of a large
mass movement, corroborates that against downstream river-gauge behaviour, and produces
a CAP-formatted alert. It is a detection system, not a forecasting one: it cannot
predict a slope failure, only hear one begin and race the water downstream.

We are writing with two specific requests and one offer.

**First, does the BIPAD portal expose a programmatic interface?** We could not determine
this from outside, and no public documentation or repository was locatable. The answer
changes our design materially. If an API exists, we would build to write alerts into
BIPAD directly. If it does not, we would emit CAP files to a location of NDRRMA's
choosing and treat BIPAD as write-only. Either is workable; guessing is not. We are not
asking for access at this stage — only for the answer.

**Second, we would like to discuss access to historical incident records** for
validating detections against recorded events. We need hazard type, date, time and
location. **We do not need, and do not want, any personal data** — no casualty records
naming individuals, no hotline transcripts, no missing-person entries. Our work is
seismic and hydrological, and the fewer categories of sensitive data we hold, the better
for everyone.

**The offer.** Several international feeds already cover Nepal continuously and free of
charge — GDACS, NASA FIRMS, NASA's landslide nowcast, GLOFAS, Google Flood Hub — and as
far as we can establish none is currently piped into a Nepali government dashboard.
Consolidating them into a BIPAD-compatible view is a few weeks of work with no research
risk. We would be glad to do that first, whatever is decided about the rest, because it
is useful immediately and it lets us demonstrate how we work before asking for anything
substantial.

We would welcome a short meeting at your convenience. If another office is the right
one for either request, we would be grateful for a redirection.

Yours sincerely,

[SIGNATORY]
[INSTITUTION]
[CONTACT]

---

## Notes for the sender — remove before sending

- The single answer that matters here is the API question (blocker B1). Everything
  else can wait; do not let the letter fail by asking for too much at once.
- The open-feed integration offer is deliberate. Handoff §18.4: institutional
  credibility is earned with early unglamorous deliverables, and it is the currency
  that later buys access to DHM telemetry and BIPAD records.
- The explicit refusal of personal data is not throat-clearing. It removes the main
  reason an agency would say no, and it is true — the project needs none of it.
- Do not mention automated public alerting. That conversation belongs at tier T1
  and after a shadow season, not in a first letter (blocker B6).
