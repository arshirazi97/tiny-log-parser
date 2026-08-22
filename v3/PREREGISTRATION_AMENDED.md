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
