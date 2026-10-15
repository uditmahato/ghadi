# Experiment 034: how much do the features depend on where the segment starts?

**Question.** Every decision is made on 120 s of signal that starts at a trigger. A mass
movement's signal grows slowly, so the trigger can fire on the first weak arrival or on
the strong waves that come later. exp031 found two Bondo stations at the same distance
with very different LF/HF and suggested the earlier trigger was the reason. A reviewer
will ask: how much do LF/HF, the centroid and H/V change with the segment start, and
would a different start rule make the classification more stable?

**Answer.** Close to the trigger the features hardly move, and no other start rule does
better than the first trigger. Starting the segment anywhere from 10 s before to 10 s
after the trigger changes LF/HF by 11 percent or less at the Nepal and Swiss stations,
the centroid by 0.04 Hz or less and H/V by 0.07 or less, and the Nepal rule gives the
same answer at every one of the eleven records. Starting later, by 30 s or more, raises
the events' LF/HF by up to about three times, but it raises the earthquakes' faster: the
share of earthquakes the Nepal rule passes goes from 22 to 50 percent in Nepal and from
51 to 86 percent in Alaska with a 30 s delay. None of the four other rules passes the
events at more stations. Every rule that moves the start later raises the share of
earthquakes the Nepal rule passes, and none lowers the station relative share by more
than a point. The first trigger stays.

Run 2026-10-15, offline, from the waveform cache.

## Results

Eleven records triggered: the 2026 event on NK.KKN and IO.EVN, Bondo on five Swiss
stations, and Taan Fiord on four Alaska stations (AK.CRQ and AK.PTPK never triggered on
it, as in exp033). Each station's earthquakes are the ones exp005, exp010, exp031 and
exp033 used, 649 in all, recomputed from the cache with the same rule as the event.

### Where the segment starts, the 2026 event

The 120 s segment slid from 30 s before to 90 s after the first trigger. The Nepal rule
needs LF/HF at least 3.94, a centroid at most 2.26 Hz and H/V at least 1.86.

| Start after the first trigger | NK.KKN LF/HF | Centroid | H/V | Earthquakes passing the Nepal rule | IO.EVN LF/HF | Centroid | H/V | Earthquakes passing |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 s before | 5.00 | 1.86 Hz | 2.34 | 22% | 14.2 | 1.56 Hz | 1.97 | 18% |
| 10 s before | 4.88 | 1.88 Hz | 2.32 | 22% | 15.0 | 1.54 Hz | 1.98 | 19% |
| **at the trigger** | **4.92** | **1.89 Hz** | **2.33** | **22%** | **15.1** | **1.53 Hz** | **1.98** | **22%** |
| 10 s after | 4.85 | 1.90 Hz | 2.32 | 28% | 15.2 | 1.53 Hz | 1.98 | 28% |
| 30 s after | 6.47 | 1.73 Hz | 2.31 | 34% | 18.5 | 1.48 Hz | 1.99 | 58% |
| 45 s after (NK.KKN), 50 s (IO.EVN) | 13.0 | 1.40 Hz | 2.04 | 45% | 34.7 | 1.36 Hz | 1.97 | 61% |
| 70 s after | 5.01 | 2.03 Hz | 1.95 | 47% | 24.5 | 1.34 Hz | 1.96 | 57% |
| 90 s after | 4.03 | 2.27 Hz | 2.09 | 50% | 17.5 | 1.48 Hz | 2.00 | 55% |

The values at the trigger are exp005's and exp010's, and the H/V values exp021's, which
checks that the segments are rebuilt the same way.

### How much each record moves

| Record | Distance | LF/HF at the trigger | Change within 10 s of it | Range over the whole slide | Nepal rule passes over the slide |
|---|---:|---:|---:|---|---|
| NK.KKN, 2026 | 56 km | 4.92 | 3% | 3.6 to 13.0 | 30 s before to 70 s after |
| IO.EVN, 2026 | 131 km | 15.1 | 7% | 14.2 to 34.7 | everywhere |
| CH.VDL, Bondo | 23 km | 3.87 | 2% | 0.90 to 3.88 | nowhere |
| CH.DAVOX, Bondo | 58 km | 1.10 | 3% | 1.00 to 3.59 | nowhere |
| CH.MUGIO, Bondo | 59 km | 3.02 | 8% | 2.31 to 3.77 | nowhere |
| CH.MMK, Bondo | 128 km | 2.50 | 7% | 2.33 to 5.75 | nowhere |
| CH.SGT05, Bondo | 128 km | 6.77 | 11% | 2.29 to 9.93 | 30 s before to 65 s after |
| AK.SAMH, Taan Fiord | 18 km | 723 | 22% | 234 to 835 | 30 s before to 70 s after |
| AK.PIN, Taan Fiord | 47 km | 131 | 28% | 27 to 131 | everywhere |
| AK.BAGL, Taan Fiord | 65 km | 255 | 44% | 117 to 368 | everywhere |
| AK.BCP, Taan Fiord | 85 km | 108 | 63% | 16 to 162 | everywhere |

Within 10 s of the trigger the centroid moves by 0.04 Hz or less at every record but
AK.BCP (0.11 Hz), and H/V by 0.07 or less at every record but AK.PIN (0.10) and AK.BCP
(0.35). The large
percentage changes in Alaska are on values 25 to 200 times the threshold.

### The candidate rules

Each rule is applied the same way to the event and to every earthquake on the same
station. "Relative" is exp032's rule: LF/HF at or above the 0.80 quantile of that
station's earthquakes and centroid at or below the 0.20 quantile, the earthquakes
measured with the same start rule, each earthquake judged against the others.

| Start rule | Events, Nepal rule | Events, relative | Earthquakes passing the Nepal rule: Nepal, Bondo, Taan Fiord | Earthquakes passing the relative rule | Decision after the first trigger | Causal |
|---|---:|---:|---|---|---:|---|
| **First trigger** (the live rule) | **7 of 11** | **10 of 11** | 22%, 1.6%, 51% | 18%, 19%, 18% | 120 s | yes |
| First trigger plus 30 s | 7 of 11 | 7 of 11 | 50%, 6.6%, 86% | 18%, 19%, 17% | 150 s | yes |
| Strongest trigger | 7 of 11 | 10 of 11 | 21%, 1.6%, 51% | 18%, 19%, 18% | 155 to 221 s | **no** |
| Envelope peak minus 30 s | 7 of 11 | 10 of 11 | 25%, 1.6%, 51% | 18%, 19%, 17% | 120 to 144 s | yes, with a delay |
| 180 s from the first trigger | 7 of 11 | 10 of 11 | 23%, 1.6%, 51% | 18%, 19%, 18% | 180 s | yes |

The same seven records pass the Nepal rule under every start rule: both Nepal stations,
CH.SGT05 and the four Alaska stations. The relative rule passes all but CH.DAVOX under
four of the rules; starting 30 s late loses CH.MMK, CH.SGT05 and NK.KKN.

## What it shows

* **The features are stable close to the trigger.** A reviewer's worry, that a few
  seconds of trigger scatter could flip the call, does not hold. Ten seconds either way
  changes nothing the Nepal rule sees on any of the eleven records. The trigger itself
  is stable too: on 630 of 649 earthquakes the first trigger near the expected arrival
  is the one `ghadi.detect.pick_onset` labels, and on 10 of 11 events the first trigger
  is also the strongest.
* **Later in an emergent signal, the events get lower in frequency, but so do the
  earthquakes, faster.** At 30 to 50 s after the trigger the 2026 event's LF/HF rises
  from 4.9 to 13 at NK.KKN and from 15 to 35 at IO.EVN. Over the same delay an
  earthquake's segment leaves its sharp P and S waves behind and fills with coda and
  surface waves, which are low in frequency too. The median earthquake's LF/HF at
  IO.EVN rises from 2.0 at the trigger to 4.7 at 30 s and 5.8 at 50 s, and the share
  passing the Nepal rule nearly triples. The
  low frequency signature is cleanest in the first two minutes after the trigger, which
  is where the rule already looks.
* **No rule does better than the first trigger.** Every rule passes the same seven
  records under the Nepal rule. The relative rule, which is the fair test because it
  measures each station's earthquakes the same way, passes ten records under every rule
  but the 30 s delay, which passes seven. Every rule that starts later raises the share
  of earthquakes the Nepal rule passes; the relative share stays within one point of the
  first trigger's under every rule. And every one delays the decision, and so the
  warning.
* **The strongest trigger is not causal.** Knowing which trigger in a search span is the
  strongest needs the whole span, and that span is anchored on a catalogue origin, which
  a live detector does not have. For the events it looks 35 to 101 s past the end of its
  own segment. It gave the same segment as the first trigger on 10 of 11 events, so
  exp031's use of it changed nothing there, but it must not be used in operation or
  presented as an alternative.
* **CH.DAVOX's low value is not about the trigger.** exp031 suggested DAVOX measured an
  LF/HF of 1.10 against MUGIO's 3.02 because it triggered 8 s earlier, on the first
  arrival. The slide says otherwise: DAVOX stays between 1.00 and 1.10 for any start
  from 30 s before to 35 s after its trigger, and fails both rules at every start. Its
  record is higher in frequency than MUGIO's whatever the start, so the difference lies
  in the site or the path, not in which arrival fired. exp031's last bullet on this
  should be read with this correction.
* **NK.KKN sits on the edge of the relative rule.** It passes the 0.80 quantile with the
  segment at or before its trigger and fails from 5 s after, where the event's LF/HF
  dips slightly and the earthquakes' rises. exp032 already found it fails at 0.85. The
  absolute rule, with its 20 percent margin, passes it at every start up to 70 s.

## What it does not show

* **It is eleven records of three events.** Stability near the trigger on these does
  not prove it for a smaller or slower event, whose trigger could fire later in the
  signal. The slide's later offsets show what such a late trigger would see.
* **The rules were judged on earthquakes, not noise.** A start rule could change the
  noise false alarm rate (exp018, exp022) differently. None of the rules was better on
  events, so the noise corpora were not rerun.
* **The Nepal corpora have no horizontals.** H/V is measured for the Nepal events and
  for the Swiss and Alaska earthquakes, but the Nepal earthquakes are judged on the two
  spectral values only, as the rule does when horizontals are missing.
* **The 180 s rule is judged against thresholds set on 120 s segments.** Its Nepal rule
  column is a check that nothing breaks, not a fair test; its relative column is fair.
* **Only one delay, one offset and one longer length were tried as rules.** The slide
  covers every delay from 30 s before to 90 s after in 5 s steps, and no delay improves
  the relative pass count over the trigger itself.

## What this means for the project

* The paper can say the decision is insensitive to trigger scatter of 10 s, and show why
  the segment starts at the trigger: the first two minutes are where a mass movement
  differs most from an earthquake on the same station.
* Nothing in the decision code changes. A later start, a longer segment or a peak
  based start each cost lead time and gain nothing.
* A causal check worth adding to the live path later: if a second, stronger trigger
  follows within the segment, record it, so a late trigger on a slow event can be seen
  in the audit log. This is a follow up, not a change made here.

## Design

`run.py` reuses exp031's and exp033's loaders and settings by importing their scripts,
and builds the Nepal records as exp005 (NK.KKN, first trigger) and exp010 (IO.EVN)
did. NK.KKN's horizontals are cached only on exp021's longer window and are cut to the
vertical's span. For every record the STA/LTA triggers (`ghadi.detect.sta_lta`) are
recomputed. An event's candidate triggers are those in its search span: 0 to 240 s after
the origin for the 2026 event and Taan Fiord, 120 s before to 240 s after the reported
time for Bondo (exp031's span). An earthquake's are those after its origin and within
90 s of its predicted P arrival, the span `ghadi.detect.pick_onset` uses. LF/HF (split
at 3 Hz) and centroid come from `ghadi.features.extract` over 120 s segments and
`spectral_features` over 180 s ones, H/V from `ghadi.features_3c.hv_ratio`, and the
Nepal rule from `ghadi.classify.classify_segment` with the default configuration. The
envelope rule smooths the analytic envelope over 5 s (the STA length), finds its peak
in the 120 s after the first trigger, and starts 30 s before the peak but never before
the trigger. "Decision after the first trigger" is the later of the segment's end and
the last moment the rule looks at.
