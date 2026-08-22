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
