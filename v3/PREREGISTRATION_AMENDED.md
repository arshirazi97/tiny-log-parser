# v3 — pre-registration, amendment 1

**Status: supersedes `v3/PREREGISTRATION.md`.** The original is preserved
unmodified. It is the record of what was predicted before the evidence below
existed, and deleting or editing it would destroy the only thing a
pre-registration is for.

Written **2026-08-22**, before the P1 corpus exists, before any v3 model is
trained, and before any of the arms have been run on anything new.

---

## Why this amendment exists

The original design was written on the assumption that v3's training labels come
from Loghub's annotations rather than from `rule_parser.py`. Four measurements
taken since show that assumption does not hold, and that two of the original
predictions could be satisfied without the hypothesis being true.

**1. The training labels are the parser's output.** Scoring
`v3/train_real.jsonl` against `rule_parser.py` on all 16,936 records — none of
which are eval lines:

| field | agreement |
|---|---|
| timestamp, level, trace_id, status_code, latency_ms | **100.0%** each |
| message | 99.1% |
| service | 95.8% |

Six-field agreement 95.8%. Nine of ten sources agree at exactly 100.0%; only
Proxifier diverges, at 63.2%. The builder never imports `rule_parser`, but
`norm_level`, `norm_service` and `ts()` reimplement the same adjudication rules,
so the output is the parser's output regardless. The original's stated safeguard
— "not from `rule_parser.py`" — was honoured in the letter and not in the fact.

Consequence: a model trained on this data distils the parser, and the original
prediction of "`service` errors < 8" is close to guaranteed without the
training-distribution hypothesis being true. That prediction can no longer
falsify anything.

**2. The existing test set cannot measure anything rules-derived.** The label
function scores **127/127 exact** on the sealed test set. Decomposed:

| arm | level | service |
|---|---|---|
| raw Loghub columns, no normalisation | 79.5% (101/127) | 82.7% (105/127) |
| + the per-source normalisation layer | **100.0%** | **100.0%** |

Zero residual across 127 held-out lines is not what a generic normaliser
produces; it is what code written against the answers produces. `rule_parser.py`
shows the same signature — 100.0% on six of seven fields. The gold labels, the
parser, and the training label function are one rule set expressed three times,
so the test set cannot distinguish 92% from 100% for any of them.

**3. The test set is additionally spent.** During the design discussion that
produced this amendment, Gemini's individual test-set failures were examined arm
by arm and field by field. Any v3 designed with that knowledge cannot be scored
on those 127 lines. This is a factual constraint on what the set can still
measure, not a matter of discipline.

**4. Loghub-2.0 is not "messy" where this schema looks.** Loghub's own
`log_format` regexes recover the header fields at **100.0%** on every system
tested — Linux (23,921 lines), Apache (51,978), Proxifier (21,320), Mac
(100,314, 626 templates), HPC (429,988). The template diversity that Loghub-2.0
adds lives inside `message`, which this schema copies verbatim. And three of
seven fields are non-null in only one system:

| field | non-null in training set | where |
|---|---|---|
| trace_id | 1,815 / 16,936 | OpenStack only |
| status_code | 998 / 16,936 | OpenStack only |
| latency_ms | 998 / 16,936 | OpenStack only |

Scaling to Loghub-2.0's 28.7M in-distribution lines drives those toward ~99.9%
null, because OpenStack is 207k of that total. More Loghub therefore makes the
task *more* regex-shaped, not less. This is why the training mix in this
amendment is not pure Loghub.

---

## What is frozen

See `v3/FREEZE_P0.txt` — six files hashed before the P1 corpus exists:
`rule_parser.py`, `build_train_real.py`, `schema_v2.py`, `score_arms.py`,
`ADJUDICATION.md`, `generate_v2.py`. Any change to those files after this point
invalidates the run.

---

## Metrics, declared now

Both are reported, in this order, whichever way they fall. Selecting the
favourable one after seeing results is the specific move that produced the v1
claim already withdrawn.

**Primary: seven-field exact.** The full schema — the record the README's
headline example shows. Chosen before the run, on the grounds that a parser
which gets six of seven fields right still emits a wrong record.

**Secondary: six-field** (excluding `message`), retained from the original for
continuity with every number already published.

---

## Predictions

Scored on the P1 corpus: fresh Loghub-2.0 templates, blind-labelled, never
touched during v3 development.

| quantity | Gemini | rules | v2 | **v3 predicted** |
|---|---|---|---|---|
| seven-field exact | 81.1% | 92.1% | 40.2% | **82 – 90%** |
| six-field | 96.1% | 92.1% | 73.2% | **88 – 95%** |
| `service` field errors | 0/127 | 10/127 | 25/127 | **< 8** |
| `level` hallucination on gold-null | 1/53 | 0/53 | 1/53 | **≤ 2/53** |

**Called in advance: v3 beats Gemini on the primary metric and loses on the
secondary.** The mechanism for the primary call is specific and was measured
before it was predicted — 19 of Gemini's 24 seven-field errors are `message`
boundary disagreements (17 OpenStack, where it swallows the `[req-…]` block or
truncates the HTTP line), and all 5 of its six-field errors are rule-compliance
failures rather than extraction failures: the T1 sentinel year twice, P1
prose-extraction three times. Convention compliance is what fine-tuning buys;
extraction capability is not.

If v3 wins the secondary metric too, that is a better result than predicted and
is reported as exceeding the prediction — not retrofitted into it.

---

## Disclosures

**The `service` and `message` coupling.** Gold `message` derives from Loghub's
`Content` column and gold `service` from `Component`. v3 trains on those same
columns. Gemini receives the same conventions as one paragraph of `SPEC_EVAL`.
This asymmetry is real, it favours v3, and it is the finding rather than a
caveat: *a 4B model given a convention as ~44,000 examples follows it more
reliably than a frontier model given the same convention in prose.* It is stated
in the results, not in a footnote.

P1's blind labelling removes the definitional half of this — gold will be
written from raw lines against `ADJUDICATION.md` without Loghub's columns
visible — but the training-side coupling remains and is not claimed away.

**Scope of any win.** Training and testing on Loghub-2.0 is an in-distribution
result. The claim is "beats the baseline on log formats it was trained on", not
"on real logs". The OOD slice carries whatever generalisation claim exists.

**Not a success criterion.** Beating Gemini is a declared prediction, not the
goal. The experiment tests whether convention compliance is learnable. Setting
the win as the goal is what produced the v1 result Andy correctly rejected.

---

## Falsification

- **`service` errors above 15** — the training-distribution hypothesis is wrong;
  a larger model or a different approach is indicated.
- **v3 below Gemini on the primary metric** — the convention-compliance
  mechanism does not hold, and the prediction above was wrong. Reported as such.
- **`level` hallucination above 2/53** — v2's abstention result did not survive
  the change of training distribution. This one is a regression, and it blocks
  shipping the model regardless of the headline numbers.

---

## Design changes from the original

**Two corpora, both new.**

- **In-distribution** — the ten systems v3 trains on, drawn from Loghub-2.0
  templates absent from both the 2k files and the existing 177-line corpus,
  blind-labelled against `ADJUDICATION.md`.
- **Out-of-distribution** — systems v3 never sees. **Corrected: BGL,
  Thunderbird, Mac, HPC.** The original listed Windows and Android; both are in
  Loghub 1.0 and **not** in Loghub-2.0. This correction is made before the run,
  not after.

**Training set: 100% real Loghub-2.0 lines.** No synthetic component. Capped at
~40 lines per template so HDFS's 11M do not drown Linux's 24k.

An earlier draft of this amendment reserved ~25% for generated abstention traps,
on the assumption that real logs contain too few. Measured before committing,
that assumption is false — the traps are abundant in Loghub-2.0 and are
therefore **mined rather than generated**:

| trap | tests | candidates in real data |
|---|---|---|
| year present in prose, gold `timestamp` = 1900 sentinel | T1 | 4,442 |
| severity word in prose, gold `level` = null | L3 / P1 | 441,478 |
| duration in prose, gold `latency_ms` = null | P1 | 21,531 |
| status code in prose, gold `status_code` = null, non-OpenStack | P1 | 1,265 |

Counts over 1.94M annotated lines across ten systems. Trap-bearing lines are
**deliberately upweighted** in the mix rather than left at natural frequency,
because finding 4 shows the natural rate would teach "always null" for three of
seven fields. The upweighting is a sampling decision, declared here, and the
sampled lines are real logs with Loghub's own annotations.

**Contamination control by `EventId`.** Loghub-2.0's own corrected template
annotations replace the five-substitution `signature()` heuristic. Enforced in
code against both corpora, verified before training.

**Known dead end, recorded now.** Proxifier has 11 templates in all of
Loghub-2.0 and the existing corpus already consumes 6; 656 lines survive
holdout. The `lifetime`-as-latency family cannot be fixed by more data. It is a
rule-level fix or a declared limitation, and it will not be presented as
anything else.

---

## Gate A

Before any training run: score the frozen `rule_parser.py` on the P1
blind-labelled corpus.

- **Rules holds near 92%** → the parser generalises, the README's headline claim
  is genuinely evidenced for the first time, and v3 proceeds.
- **Rules falls to 75–80%** → the published 92.1% was fitting. Stop. Correct the
  README before building anything on top of it.

Both outcomes are worth the cost of P1 on their own, independent of whether v3
is ever trained.

---

## Budget

~$2.40 P1 labelling · ~$5 GPU (3 runs) · ~$5.60 baseline API · **~$13 total.**

## P1 sampling parameters — declared 2026-08-22, before the corpus exists

Recorded here rather than left to the sampler's source so the numbers cannot be
adjusted after seeing how the draw came out.

| parameter | value |
|---|---|
| in-distribution lines | **200** (10 systems × 20) |
| out-of-distribution lines | **100** (4 systems × 25) |
| seed | `20260822` |
| one line per `EventId` | longest instance, from at most 5 candidates |

Quotas are ceilings. A system with fewer unspent templates than its quota
contributes what it has, and the shortfall is reported in `P1_FREEZE.txt`
rather than backfilled from a system with spare templates — backfilling would
silently reweight the corpus toward whichever systems happen to be template-rich.

**Blind labelling, enforced by file layout.** `build_corpus_p1.py` writes the
raw lines to `corpus_p1.jsonl` and Loghub's columns to `p1_sidecar.jsonl`.
Only the former is opened during labelling. The sidecar exists to measure
label-vs-Loghub agreement *after* labels are frozen, which is a result, not an
input. Linux is the clearest reason this matters: its `Level` column holds
`combo`, the hostname, and a labeller who saw it would be anchored to a value
`ADJUDICATION.md` says is not a level.

**Holdout.** An `EventId` is dropped if any of its lines' `Content` appears in
that system's 1.0 `*_2k` annotations; the selected line is dropped if its
template signature matches a `*_2k` or existing-corpus line. Verified by
running the sampler against the 1.0 data as if it were 2.0: every template is
correctly rejected and the draw is empty.

## Reproducibility correction — 2026-08-22

Finding 4's figures above were measured in a session that no longer exists, and
no script in this repository reproduced them. `v3/measure_loghub2.py` now
recomputes them, with its operationalisations documented in the source, and
writes `v3/MEASUREMENTS_P1.txt`. It runs before sampling.

If the recomputed figures disagree with finding 4, the disagreement is recorded
as a correction and the design decisions that rested on those figures —
trap mining over trap generation, and the upweighting — are revisited before
the corpus is drawn. Finding 4 is not edited to match.

## Correction — 2026-08-22: Loghub-2.0 annotates no header fields

Measured on the downloaded release (Zenodo record 8275861), the structured CSV
for every system checked — Linux, Apache, Proxifier, HPC — has exactly four
columns:

    LineId,Content,EventId,EventTemplate

Loghub **1.0** ships rich per-system headers (`Linux_2k.csv` is
`LineId,Month,Date,Time,Level,Component,PID,Content,EventId,EventTemplate`).
Loghub-2.0 drops all of them. It annotates the message body and the template,
and nothing else.

**Finding 4 survives this and is confirmed.** Line counts match to the digit —
Linux 23,921, Apache 51,978, Proxifier 21,320, HPC 429,988 — Proxifier's 11
templates are confirmed, and header recovery is 100.0% on all three systems
where it was claimed. One correction to method: recovery must be measured under
collapsed whitespace, because 2.0 normalises runs of spaces inside `Content`.
Measured literally, Linux reads 81.6%; the 4,406 mismatches are every one of
them a doubled space. The 100.0% claim is right and the naive measurement of it
is wrong.

**What this does change is P2, not P1.** P1 is unaffected: gold is hand-written
from raw lines against `ADJUDICATION.md`, which never needed Loghub's columns.

The training plan does not survive intact. "Training set: 100% real Loghub-2.0
lines" assumed those lines carry `level` and `service` annotations. They do not.
The available sources for a P2 label are:

| field | Loghub-2.0 provides | consequence |
|---|---|---|
| `message` | `Content`, directly | genuine third-party annotation |
| template identity | `EventId` / `EventTemplate` | genuine, and drives holdout |
| `timestamp`, `level`, `service` | nothing | must be derived from the raw line |
| `trace_id`, `status_code`, `latency_ms` | nothing | already ours, already disclosed |

Deriving `level` and `service` from the raw line means deriving them by rule,
which is precisely the coupling finding 1 identified: a model trained on that
data distils `rule_parser.py`. Scaling from 1.0 to 2.0 does not escape the
coupling — it deepens it, because 1.0 at least supplied `Level` and `Component`
from a third party for nine of ten systems, and 2.0 supplies neither for any.

This is recorded now, before P1 runs, because it bears on whether P2 is worth
running at all. It is not resolved here. **Gate A is unaffected and proceeds** —
it scores the frozen parser against hand-written labels and needs no training
data. The P2 label question is settled after Gate A reports, on the evidence
Gate A produces.

## Correction — 2026-08-22: finding 4's trap counts, recomputed

Full output in `v3/MEASUREMENTS_P1.txt`, over all 50,416,623 annotated lines of
Loghub-2.0. Restricted to the ten in-distribution systems — the only ones a v3
training mix may draw from — against finding 4's table:

| trap | finding 4 | measured (in-dist) | |
|---|---|---|---|
| T1 year in prose | 4,442 | **4,442** | exact |
| P1 duration in prose | 21,531 | 545,711 | 25× |
| P1 status in prose | 1,265 | 247 | 0.2× |
| L3 severity in prose | 441,478 | **3,224** | 0.007× |

**T1 reproduces exactly**, which is strong evidence the original measurement
was sound and ran over the full data. It also settles the denominator: finding
4 says "counts over 1.94M annotated lines across ten systems", but the ten
in-distribution systems hold **28,653,315** annotated lines, and T1's 4,442
requires all of Linux, OpenSSH and Proxifier. The 1.94M is a mis-stated
denominator, not a different measurement.

**Duration and status are definitional.** Duration differs by roughly the
denominator ratio; the matches are genuine trap candidates — Proxifier's
`lifetime <1 sec` (the exact `lifetime`-as-latency family) and Linux's
`Commit interval 5 seconds`. Status is narrower here, requiring a
`status`-keyword or `HTTP/1.x` context rather than a bare three-digit number.

**L3 does not reconcile, and this one changes a design decision.** 3,224
candidates across 28.65M in-distribution lines is a density of **0.011%**.
441,478 from 1.94M lines requires 22.8%, and no system in Loghub-2.0 reaches
it — the highest are HPC at 14.2%, Thunderbird at 12.8%, Mac at 12.1%, all
three of them **out-of-distribution systems v3 is forbidden to train on**. The
in-distribution systems that carry a real `Level` column contribute zero by
construction, because their gold `level` is not null.

Consequence: **the claim that severity-in-prose traps are abundant enough to
mine rather than generate is not supported for `level` on in-distribution
data.** The earlier draft's assumption — that real logs contain too few, and
the traps must be generated — was rejected in this amendment on the strength of
the 441,478 figure. That figure does not survive recomputation, so the
rejection does not stand.

This matters more than the other three because `level` is the field the v2
abstention result was about, and `level` hallucination above 2/53 is a declared
shipping blocker. A training mix that teaches "always null" for `level` is the
specific failure the upweighting existed to prevent.

**Not resolved here, and deliberately so.** P1 and Gate A do not depend on any
of this: the corpus is sampled by `EventId` quota and gold is hand-written.
The P2 mix is designed after Gate A reports, against these numbers rather than
the originals.

## How Gate A is read — declared 2026-08-22, before labelling

The P1 corpus is drawn: **262 lines, 162 in-distribution and 100 OOD.** Three
systems came in under quota, as the ceiling rule anticipated: OpenStack 5/20,
OpenSSH 16/20, Proxifier 1/20. OpenStack and Proxifier are structural — they
hold 48 and 11 templates in all of Loghub-2.0, and the existing corpus already
spent 43 and 6. No sampling change recovers them.

**OpenStack's shortfall is not a lost 15 lines, it is three fields.** On the
existing test set `trace_id` (24/127), `status_code` (14/127) and `latency_ms`
(14/127) are non-null *only* on OpenStack lines, and OpenStack was 18.9% of
that corpus. In P1 it is 1.9%. P1 will carry roughly five lines with a
`trace_id` and three each with a `status_code` and a `latency_ms`.

Declared now, before any label is written:

1. **Gate A is reported per-field and per-system, not as a single number.**
   The published 92.1% was measured on a differently-composed corpus, so a
   headline-to-headline comparison confounds generalisation with composition.
   The per-system table is the comparison that means something.

2. **On P1, `trace_id`/`status_code`/`latency_ms` test abstention, not
   extraction.** Roughly 257 of 262 lines are gold-null for them. Whether the
   parser invents a latency from Proxifier's `lifetime <1 sec` is exactly the
   P1 trap and is worth measuring. Whether it can *extract* those fields is not
   evidenced by this corpus, and the existing test set remains the only
   evidence for it. Any v3 claim about those three fields says so.

3. **The Gate A threshold applies to the fields P1 actually exercises** —
   `timestamp`, `level`, `service`, `message`. "Rules holds near 92%" is judged
   there. A seven-field number is also reported, and is not the gate.

None of this is a reason to re-draw. Re-drawing a corpus after seeing its
composition is the post-hoc adjustment this document exists to prevent, and the
quotas were declared as ceilings precisely so a shortfall would be reported
rather than engineered away.

## Label provenance — recorded 2026-08-22, before Gate A runs

The P1 gold labels are **not hand-written**, and the results say so.

| field | source | n |
|---|---|---|
| `message` | Loghub-2.0 `Content` column | 96 |
| timestamp, level, service, trace_id, status_code, latency_ms | Claude (Opus 5) applying `ADJUDICATION.md` | 94 records |
| the same six | hand-written by the author | 2 records |

Recorded per field per record in `label_source`, so the split is legible in the
data and not only here.

**What this costs Gate A.** `rule_parser.py` implements `ADJUDICATION.md`. A
model applying that same document produces labels that agree with the parser
wherever the parser implements its spec. Gate A therefore **cannot test whether
the parser generalises to unseen templates** — it tests spec-conformance, which
was never in doubt. This is finding 2 of this amendment reappearing in a new
place, and it is stated rather than worked around.

Consequence for the README: the published **92.1% is not evidenced by P1**. It
stays as it is, or it is softened. It is not upgraded on the strength of a Gate
A run against labels written from its own rulebook.

**Why no third-party check offsets this.** Loghub-2.0's structured CSV is
`LineId, Content, EventId, EventTemplate` only. It annotates no `Level` and no
`Component`, so `validate_labels_loghub.py` — the independent corroboration that
supported the previous corpus at 127/127 on `level` — **cannot run on P1 at
all**. `message` is the single field with third-party provenance, and it is
taken directly rather than checked.

**Author review, and its weight.** All 96 records were reviewed by the author in
`review_ui.py`: 95 approved unchanged, 1 edited and then restored to its
original value. That is a **review agreement of 96/96**, and it is reported as
review agreement, not as independent agreement. A reviewer shown a proposed
value tends to assent to it; the number bounds gross error, not systematic
error. If `S1b` was read wrongly, review would not catch it.

**The blind spot-check, declared before it runs.** 25 of the 96 records, drawn
by `random.Random(20260822).shuffle` over the sorted id list, are re-labelled by
the author from the raw lines alone. `label_ui.py --spotcheck 25` neither loads
nor displays the gold, and writes to a separate `spotcheck_p1.jsonl`.
`spotcheck_compare.py` then reports six-field exact agreement and per-field
agreement.

That figure is published with the results whichever way it falls. It is the only
independent measure of label quality this corpus admits. It does not restore
Gate A's ability to test generalisation — nothing can, given the label
provenance — but it bounds how much weight the gold can carry.

**Four in-distribution lines could not be labelled** and are in
`ambiguous_p1.jsonl` rather than guessed: three HealthApp lines whose date is
`201812`, six digits where the format is `yyyymmdd`, and one Spark line that is
a Java stack-trace continuation with no timestamp, level or logger position.
Both are properties of Loghub-2.0 that the ten-system corpus never surfaced, and
both are reported.

## Blind spot-check result — 2026-08-22, before Gate A was run

25 of the 96 gold records, drawn by `random.Random(20260822)` over the sorted id
list, re-labelled by the author from the raw lines alone. The gold was neither
loaded nor sent to the browser.

**Six-field exact agreement: 21/25 (84.0%).**

| field | agreement |
|---|---|
| timestamp | 25/25 |
| level | **25/25** |
| status_code | 25/25 |
| latency_ms | 25/25 |
| trace_id | 24/25 |
| service | 22/25 |

`level` at 25/25 covers every line whose correct value is null — Linux, OpenSSH,
HealthApp — including two OpenSSH lines carrying `error:` in the message text.
The L1/L3 abstention call was reproduced independently.

**The four disagreements, adjudicated against the raw lines:**

| line | gold | spot-check | resolution |
|---|---|---|---|
| OpenStack trace | `…-46b0-…` | `…-4b60-…` | **transcription slip** — the line reads `46b0`; gold matches, spot-check does not |
| Linux `named[2305]:` | `named` | null | **slip** — service was filled on the other three Linux lines |
| Zookeeper `…:Environment@100]` | `Environment` | null | **slip** — filled on the other Zookeeper line |
| Zookeeper `[main:QuorumPeer@959]` | `QuorumPeer` | `main:QuorumPeer@959` | **genuine rule disagreement** |

Only the last is a difference of reading. S1b says take the class immediately
before `@<line>`, so the written rule favours the gold — but S1b was itself added
after the previous corpus forced it, and it is evidently not self-evident on
first encounter. Recorded as a known ambiguity in the rule rather than as
labeller error.

**What this supports.** The gold is model-written; an independent human pass over
a seeded random quarter of it agrees on 84% of six-field records and 100% of
`timestamp` and `level`, with three of the four disagreements being
transcription slips rather than differing readings.

**What it does not support.** It does not restore Gate A's ability to test
whether `rule_parser.py` generalises. The gold still comes from the parser's own
rulebook. The spot-check bounds label quality; it does not decouple the labels
from the arm being scored.

## Extending the blind set to n=96 — declared 2026-08-22, before the extra labels exist

The 25-line spot-check returned 84.0% six-field with a 95% interval of [68, 96],
which contains both Gate A branches. The remaining **71** of the 96 gold records
are now blind-labelled by the author so the gate can be decided at full n.

**This is a decision to collect more data taken after seeing a result, and it is
declared rather than hidden.** Three things make it legitimate here:

1. **It goes to the full set, not to a chosen stopping point.** All 71 remaining
   records are labelled. There is no n at which the author may stop early, and
   therefore no discretion to stop on a favourable reading.
2. **The decision rule was fixed first.** Gate A's thresholds — near 92% versus
   75–80% — were written before the corpus existed, and are unchanged.
3. **84.0% fell inside the ambiguous band.** The stopping rule already recorded
   above resolves the gate outright above 88% or below 82% and extends to the
   full set in between. 84.0% is in between.

The same shuffle governs: `random.Random(20260822)` over the sorted id list, with
the first 25 being those already labelled. Verified: the 25 completed records are
exactly the first 25 of that ordering, and `label_ui.py --spotcheck 96` resumes at
record 26 without loading or displaying any gold.

**What the result will and will not settle.**

At n=96 independent the 95% interval narrows to roughly ±6pp, which separates 92%
from 78%. So this decides whether the published 92.1% survives against labels
that did not come from the parser's own rulebook.

It still does not make the *model-written* gold independent, and Gate A against
`labels_p1.jsonl` remains uninformative at 100.0%. The figure that counts is the
parser scored against `spotcheck_p1.jsonl`. That is the number reported as Gate A
from here, and the 96-record run is reported alongside it as the measure of the
coupling rather than as a result.

Whichever way it falls is published, including the branch where the README's
92.1% has to be corrected.

## Gate A result — 2026-08-22

All 96 gold records were blind-labelled a second time by the author, from the raw
lines alone, with the gold neither loaded nor displayed. The parser was then
scored against those independent labels.

**`rule_parser.py` vs independent labels, six-field: 72.9% as labelled (n=96),
84.4% after correcting two provable labelling errors. 95% CI [75.8, 90.3].**

### Adjudication

| | six-field | |
|---|---|---|
| as labelled | 72.9% | |
| correcting the HDFS sub-second error | 83.3% | 10 lines |
| correcting the trace-id transposition | **84.4%** | 1 line |
| additionally excluding Zookeeper `service` | 97.9% | 13 lines — **not applied** |

**The HDFS correction is factual, not generous.** On all ten HDFS disagreements
the author's sub-second digits are the leading digits of the **PID column**
(`.205` from PID `20570`, `.418` from `4185`, `.016` from `16`, 10/10). HDFS's
format is `yymmdd hhmmss pid LEVEL component:` and carries no sub-second field,
so those digits provably come from a different column. Same for the trace id:
the line reads `46b0`, the author wrote `4b60`.

**The Zookeeper divergence is left standing, and it is the substantive finding.**
On 13 of 14 remaining `service` disagreements the author labelled Zookeeper
`service` as null where S1b takes the class before `@<num>` — `Follower`,
`Environment`, `SessionTrackerImpl`, `FastLeaderElection`, `CommitProcessor`,
`Leader`, `FileTxnLog`, `QuorumPeer`. The behaviour is consistent across both the
n=25 and n=96 passes, and the same author filled `service` for Linux, HDFS,
Spark, Hadoop and HealthApp, so it reads as a position rather than fatigue: in
`[QuorumPeer[myid=1]/0:0:0:0:0:0:0:0:2181:Follower@118]`, `Follower` is a class
name inside a thread descriptor and arguably not a service at all.

Recorded as a genuine second-annotator disagreement with S1b. It is **not**
excluded from the score. If the author later confirms these were uncertainty
rather than judgment, the figure moves to 97.9% and this section is amended
rather than rewritten.

### Verdict

Gate A's declared branches were "rules holds near 92% → v3 proceeds" and "rules
falls to 75–80% → the published 92.1% was fitting; stop and correct the README".

**The falsification branch fires.** 84.4%, Wilson 95% CI [75.8, 90.3], **excludes
92.1%** and contains the 75–80% band. The published figure does not survive
contact with labels that did not come from the parser's own rulebook.

The two fields that do survive independently:

| field | vs independent labels |
|---|---|
| `level` | **100.0%** (96/96) |
| `status_code`, `latency_ms` | 100.0% |
| `trace_id` | 97.9% |
| `timestamp` | 89.6% → 100% after the PID correction |
| `service` | 85.4% |

`level` at 96/96 covers every gold-null line across Linux, OpenSSH, HealthApp and
Proxifier. **The abstention result is the part of this project that survives an
independent corpus.** The extraction accuracy claim is the part that does not.

### Consequence

The README's 92.1% is corrected, not deleted: it remains the measurement on the
original corpus, and it is now reported alongside 84.4% on an independent one.
S2c-style rule ambiguity in S1b is disclosed as an open question rather than
settled in the parser's favour.

## S1b confirmed as disputed — 2026-08-22

Asked directly whether the 13 Zookeeper `service` nulls were a judgment or
uncertainty, the author confirmed the reading: **null**, with the qualifier
"I think". Recorded with that qualifier rather than firmed up.

Consequences:

1. **84.4% stands as the Gate A figure.** The 97.9% variant, which excludes
   Zookeeper `service`, is not the reported number.

2. **S1b is a disputed rule, not a settled one.** It says take the class
   immediately before `@<num>`, so
   `[QuorumPeer[myid=1]/0:0:0:0:0:0:0:0:2181:Follower@118]` yields `Follower`.
   Re-reading the same lines without seeing the rule's output, the author who
   wrote S1b labelled those lines null on 12 of 13 occasions. A rule its own
   author does not reproduce on a blind second pass is not a rule a third party
   would reproduce either.

3. **`rule_parser.py` is wrong on every Zookeeper line under this reading**, and
   that single rule accounts for 13 of the 15 remaining field disagreements —
   most of the gap between 84.4% and 97.9%.

4. **`ADJUDICATION.md` is frozen and is not edited.** The dispute is recorded
   here. Any resolution belongs in a successor file with its own freeze, and
   must be declared before it is applied to any score.

This is the same failure mode as S2c, which moved 10 test labels after
`validate_labels_loghub.py` contradicted the original reading. Two of the
schema's `service` rules have now failed to survive independent re-reading. The
honest generalisation is that **`service` is under-specified for
bracket-nested logger formats**, and that this — not the headline percentage —
is what a successor schema has to fix.
