# P2/P3/P4 — pre-registration

Written **2026-08-23**, before any training data is generated, before any model
is trained, and after Gate A has been decided and reported. Supersedes nothing;
`PREREGISTRATION_AMENDED.md` stands, including the parts it got wrong.

---

## What changed since the original P2 plan

The original design said *"Training set: 100% real Loghub-2.0 lines. No synthetic
component."* Two P1 findings retire it:

1. **Loghub-2.0 annotates no header fields.** Its structured CSV is
   `LineId, Content, EventId, EventTemplate`. There is no `Level` and no
   `Component`, so `timestamp`, `level` and `service` cannot come from Loghub.
2. **The trap count that killed the synthetic component was wrong.**
   `L3_severity_in_prose` was claimed at 441,478; it measures **3,224** across
   the ten in-distribution systems, a rate of 0.011%. Real logs do not contain
   enough abstention traps to teach abstention. The slide this amendment
   overruled — *75% Loghub-2.0, 25% targeted synthetic* — was right.

## The hypothesis

v2's failures on real logs are **two specific, nameable families**, not a general
capability limit, and both are teachable with targeted data.

Measured on P1 against independent human labels, the v2 fine-tune's 23 field
errors are:

| family | n |
|---|---|
| `service` = the thread token, or the dotted logger shortened to its last segment | 12 |
| `latency_ms` invented from a duration in the message text | 8 |
| `status_code` invented | 2 |
| unparseable JSON | 1 |

These are the same two families named in `v3/PREREGISTRATION.md` before the P1
corpus existed. The diagnosis has now held across two corpora from different
Loghub releases.

## The ceiling, stated before the run

Decomposing the 96 P1 lines by whether each arm is correct:

| | n |
|---|---|
| parser and fine-tune both correct | 58 |
| **parser only — recoverable headroom** | **23** |
| fine-tune only | **0** |
| neither — the teacher fails these too | 15 |

**The fine-tune has zero wins the parser does not have.** Its ceiling under this
design is therefore exactly the parser's score, **84.4%**, and 22 of the 23
recoverable lines fall in the two targeted families (`service` 14,
`latency_ms` 8).

**This experiment cannot produce a win over `rule_parser.py`.** The parser is the
teacher for 75% of the training signal and the fine-tune has no wins the parser
lacks, so 84.4% is a hard ceiling. Any framing that implies otherwise is the v1
error repeated.

**It can, in principle, beat gemini-3.1-pro-preview.** Gemini scores 78.1%
(75/96) on the same lines against the same labels, which is 6.3 points below the
ceiling. Passing it requires 76/96 — recovering 18 of the 23 headroom lines, or
roughly 78% of the available gap.

*Correction, 2026-08-23:* an earlier draft of this document asserted that a win
over Gemini was impossible. That was wrong — it confused the parser ceiling with
Gemini's score. The error is recorded rather than edited away, because the
prediction band below (74–82%) was written under it and straddles Gemini either
way.

**Beating Gemini is a possible outcome, not the success criterion.** The
experiment tests whether a named failure diagnosis is actionable. Declaring the
win as the goal is what produced the v1 result Andy correctly rejected.

## Design

**Training mix — 75% real / 25% targeted synthetic.**

| portion | source | labels | rationale |
|---|---|---|---|
| ~75% | Loghub-2.0 lines, `EventId`-held-out | `rule_parser.py` | real format diversity; v2 failed because it met real logs first at test time |
| ~25% | new renderers, `v3/generate_v3.py` | exact by construction | the two families are 0.011%-rare in real data and cannot be learned from it |

**The coupling is disclosed, not claimed away.** Three quarters of the training
signal is the parser's output, and Gate A measured the parser at 84.4% against
independent labels. The model is being distilled from a teacher that is wrong
16% of the time, and its ceiling is that teacher's accuracy.

**`generate_v2.py` is frozen** in `FREEZE_P0.txt` and is not edited. New
renderers land in `v3/generate_v3.py`, per that file's own note.

### The two synthetic families

**F1 — thread-then-logger.** Lines where a thread descriptor precedes or encloses
the logger, and the tempting answer is the thread:

```
2015-10-17 21:48:50,260 INFO [main] org.apache.hadoop.mapred.MapTask: ...
   gold service = org.apache.hadoop.mapred.MapTask      (not "main")
2015-07-29 19:04:29,071 - WARN  [SendWorker:188978561024:QuorumCnxManager$SendWorker@688] - ...
   gold service = QuorumCnxManager$SendWorker           (not "SendWorker")
```

Both shapes are generated with varied thread names, varied logger depth, and the
full dotted path preserved (S1 forbids shortening to the last segment).

**F2 — duration in prose, gold `latency_ms` null.**

```
... finished in 6.049 s              -> latency_ms: null
... 59728 millis timeout left        -> latency_ms: null
... Sleeping for 0ms before retrying -> latency_ms: null
... elapsedRealtime(): 29950         -> latency_ms: null
```

Paired against lines where a duration **is** in a structural position and
`latency_ms` is non-null, so the model learns the distinction rather than
"always null".

**Contamination control.** No line in `corpus_p1.jsonl`, `corpus_dev.jsonl` or
`corpus_test.jsonl`, and no line sharing an `EventId` or template signature with
one, may enter training. Enforced in code and verified before training, as in P1.

## Predictions

Scored on the **96 P1 lines against `spotcheck_p1_adjudicated.jsonl`** — the
independent human labels. The rules and Gemini predictions already exist and are
not re-run.

| quantity | v2 (measured) | ceiling | **v3 predicted** |
|---|---|---|---|
| six-field exact | 60.4% | 84.4% | **74 – 82%** |
| `service` errors | 14 / 96 | 0 | **< 6** |
| `latency_ms` errors | 8 / 96 | 0 | **< 3** |
| `level` hallucination on gold-null | **0 / 32** | — | **0 / 32** (must not regress) |
| unparseable JSON | 1 / 96 | 0 | ≤ 1 |

74–82% corresponds to recovering roughly 60–90% of the 23-line headroom.

## Falsification

- **Six-field at or below 66%** — under a quarter of the headroom recovered. The
  failure families are not teachable this way and the hypothesis is wrong.
  Reported as such.
- **`service` errors above 10** — the thread-then-logger family did not transfer
  from synthetic to real. This is the larger half of the headroom and the main
  thing being tested.
- **`level` hallucination above 0/32** — a regression. v2's one surviving result
  is abstention on `level`; trading it for extraction accuracy is a net loss and
  blocks shipping regardless of the headline.

## What gets reported either way

The four-arm table on the P1 corpus — rules, Gemini, v2, v3 — against independent
labels, with McNemar between v2 and v3. If v3 does not beat v2, that is the
result. If it does, the ceiling and the coupling are stated in the same
paragraph as the number.

## Budget

~$5 GPU (RunPod, ~2.5 h) · $0 scoring (rules and Gemini predictions already
exist) · **~$5 total.**
