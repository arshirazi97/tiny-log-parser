# tiny-log-parser — v3

**Repo:** https://github.com/arshirazi97/tiny-log-parser
**Full record:** [`v3/PREREGISTRATION_AMENDED.md`](v3/PREREGISTRATION_AMENDED.md) · [`real-eval/RESULTS_P1.md`](real-eval/RESULTS_P1.md)

---

## What v3 set out to do, and what it found instead

v3 was going to fine-tune a 4B model on real logs and see whether it beat a
frontier baseline. It never got that far, because the gate in front of it
failed — and the failure is the result.

**The rules parser's published 92.1% was measured against labels derived from
its own rulebook. On labels that were not, it scores 84.4%.**

---

## The setup

`rule_parser.py` is a deterministic parser. `ADJUDICATION.md` is the written rule
list it implements. The v2 evaluation labelled 127 real log lines against that
rule list — model-drafted, author-reviewed, disclosed as such — and the parser
scored **92.1%** six-field.

The obvious objection was already in the README: *the rules arm shares an author
with the labels.* v3's first phase, P1, was built to find out how much that
mattered.

## P1 — a second corpus

262 lines drawn from Loghub-2.0 (Zenodo `8275861`, 50.4M annotated lines across
14 systems), seeded and frozen. Contamination controlled by `EventId` and
verified, not assumed: **zero** raw-line overlap and **zero** template-signature
overlap with the original corpus. The sampler was tested by pointing it at
Loghub 1.0 dressed as 2.0 — every template was correctly rejected and the draw
came back empty.

96 in-distribution lines were labelled twice:

- **Pass 1** — a model applying `ADJUDICATION.md`, author-reviewed. Same method
  as v2.
- **Pass 2** — the author, from the raw lines alone, with pass 1 neither loaded
  nor displayed.

## The coupling, measured

| gold used | rules six-field |
|---|---|
| model labels from `ADJUDICATION.md` | **100.0%** |
| the author's independent labels | **84.4%** |

100.0% is not a good score. It is what happens when the answer key and the system
under test are two expressions of one rule set. The parser did not improve; the
gold moved toward the parser.

84.4% is the number, 95% CI **[77.1, 90.6]**. The pre-registered
falsification threshold — written before the corpus existed — was 75–80%. The
interval contains it and **excludes 92.1%**.

Two corrections were applied to the independent labels before scoring, both
factual rather than generous:

- **Ten HDFS timestamps** where the annotator's sub-seconds are the leading
  digits of the **PID column** (`.205` from PID `20570`, `.418` from `4185`,
  10/10). HDFS's format carries no sub-second field.
- **One transposed trace id** — the line reads `46b0`, the annotator wrote
  `4b60`.

Raw, before those corrections, the figure is 72.9%.

## The finding worth more than the percentage

Thirteen of the fifteen remaining disagreements are one rule.

`ADJUDICATION.md` rule **S1b** says: in a Zookeeper bracket, take the class
immediately before `@<num>`. So
`[QuorumPeer[myid=1]/0:0:0:0:0:0:0:0:2181:Follower@118]` yields `Follower`.

Re-reading those lines blind, **the author who wrote S1b labelled them null on 12
of 13 occasions** — and filled `service` normally for Linux, HDFS, Spark, Hadoop
and HealthApp, so it is a position rather than fatigue. In that bracket,
`Follower` is a class name inside a thread descriptor, and calling it *the
service* is a stretch.

This is the second `service` rule to fail independent re-reading. **S2c** already
moved 10 test labels in v2 after Loghub's own annotations contradicted the
original call.

> A rule that its own author does not reproduce on a blind second pass is not a
> rule a third party will reproduce either. `service` is under-specified for
> bracket-nested logger formats, and that is a schema defect, not a scoring
> detail.

## Three arms, re-measured

All three arms were then scored on the same 96 lines, against the labels written
blind:

| arm | six-field | 95% CI |
|---|---|---|
| **rules** | **84.4%** | 77.1 – 90.6% |
| gemini-3.1-pro-preview | 78.1% | 69.8 – 86.5% |
| Qwen3-4B fine-tune (v2) | 60.4% | 50.0 – 70.8% |

McNemar, paired: rules beats Gemini 6–0 (p=0.031), rules beats the fine-tune 23–0
(p<0.0001), Gemini beats the fine-tune 20–3 (p=0.0005). Strict ordering, no
discordant pair lost by the parser.

**A 250-line deterministic parser beats a frontier model on this corpus.** Not
by much, and not transferably — 96 lines with a composition unlike the previous
corpus — but measured against labels neither arm's author wrote from a rulebook.

## The abstention result held

| non-null where gold is null | rules | gemini | fine-tune |
|---|---|---|---|
| **level** | **0 / 32** | 2 / 32 | **0 / 32** |
| status_code | 0 / 96 | 1 / 96 | 2 / 96 |
| latency_ms | 0 / 96 | 2 / 96 | 8 / 96 |

On `level`, the 4B fine-tune matched the deterministic parser and **beat
gemini-3.1-pro-preview** — on formats it has never seen, against labels written
blind by a human. v2 predicted this in advance and it survives an independent
corpus.

Its extraction is where it loses: `service` 70.8%, `latency_ms` 90.6% with eight
invented values. *Abstention is learnable per-field; extraction is not.*

## What survived

| field | vs independent labels |
|---|---|
| **`level`** | **100.0%** (96/96) |
| `status_code`, `latency_ms` | 100.0% |
| `trace_id` | 97.9% |
| `timestamp` | 100.0% after correction |
| `service` | 85.4% |

`level` at 96/96 covers **every gold-null line** across Linux, OpenSSH,
HealthApp and Proxifier — including lines whose message text literally contains
`error:`. Knowing when *not* to emit a field is the part of this project that
holds up against an independent annotator.

## Corrections to the pre-registration itself

P1 was also a check on the amendment's own numbers, and two things came back.

**Confirmed.** Header recovery is 100.0% on all 14 Loghub-2.0 systems. Line
counts match to the digit (Linux 23,921, Apache 51,978, Proxifier 21,320, Mac
100,314 / 626 templates, HPC 429,988). The in-distribution total is 28,653,315.
The T1 trap count recomputes to **4,442** — exactly as claimed.

**Wrong by three orders of magnitude.** The `level`-trap count was claimed at
441,478. It measures **3,224** across the ten in-distribution systems, a density
of 0.011%. The original figure has the density signature of Thunderbird, Mac and
HPC — out-of-distribution systems the training set may not draw from. The
decision that rested on it, *mine the traps rather than generate them*, does not
stand.

**Loghub-2.0 annotates no header fields.** Its structured CSV is
`LineId, Content, EventId, EventTemplate` — no `Level`, no `Component`. So
`validate_labels_loghub.py`, the third-party check that corroborated v2's labels
at 127/127 on `level`, cannot run on any Loghub-2.0 corpus. It also means a
training set built from Loghub-2.0 would have to derive `level` and `service`
from the parser, which is the coupling this whole exercise measured.

## Status

| phase | |
|---|---|
| P0 — freeze and declare | done |
| P1 — second corpus, independently labelled | done |
| **Gate A** | **falsification branch fired** |
| P2–P4 — training set, train, score | not run |

P2 assumed the parser was a baseline worth distilling and that Loghub-2.0
supplied the labels to do it with. Neither holds.

## What this is worth

The headline is a number going down. What is actually on offer is an evaluation
that was tested against its own weakest assumption, in public, with the
falsification threshold fixed in advance — and reported when it fired.

The v1 claim was withdrawn because the test set came from the generator. The v2
claim is now corrected because the labels came from the rulebook. Both were found
by looking for them.
