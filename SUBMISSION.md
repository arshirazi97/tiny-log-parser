# tiny-log-parser v3 — a 4B specialist against a frontier model

**Abdul Rehman · 24 August 2026**
Repo: https://github.com/arshirazi97/tiny-log-parser · tag `v3-final`
Run it: [heldout.ipynb in Colab](https://colab.research.google.com/github/arshirazi97/tiny-log-parser/blob/main/heldout.ipynb)
 — verifies the split, runs v3, and takes your own logs.

## The task

Normalise an arbitrary log line into a canonical seven-field JSON record —
`timestamp, level, service, trace_id, status_code, latency_ms, message` —
emitting `null` for fields the line does not carry rather than inventing them.
Abstention is the hard part: a model that infers `ERROR` from the word "failure"
is wrong, and that error is invisible to any metric that only counts extraction.

## What changed since v2

At the v2 submission I said: *"Agreed, it didn't beat it. I'd train it on real
logs too, not just test on them, and have numbers by Monday."* Both halves are
delivered here.

| | v2 | v3 |
|---|---|---|
| training data | 100% synthetic (`generate_v2.py`) | **75% real Loghub** — 8,046 lines, 10 systems |
| total examples | 20,000 | 10,728 (8,046 real + 2,682 targeted synthetic) |
| base | Qwen3-4B, 4-bit + LoRA | same |

The synthetic quarter is not filler: four families target specific adjudication
rules (nested thread brackets, prose-vs-structural durations) that real logs do
not contain densely enough to teach.

## Method — and the part that went wrong

Contamination control was pre-registered before training and enforced in code:
the builder compares every training line against every evaluation line at
**template signature** level, not just string equality, and aborts rather than
warns.

**It had a bug.** The signature masked digits, IPs, hex and paths — but not
textual month names. So these two signed differently and crossed the boundary
undetected:

```
EVAL   [Thu Jun 09 06:07:19 2005] [notice] Digest: done
TRAIN  [Thu Jan 26 12:23:07 2006] [notice] Digest: done
```

Fixed, then re-verified. The corrected guard found **59 evaluation lines the old
one had passed**, including one in the sealed test set. The headline evaluation
corpus turned out to be **22% template-contaminated**, and the 99.0% figure it
produced has been discarded.

Removing the contamination cost 15 points:

| corpus | contamination | v3 | gemini-3.1-pro |
|---|---|---|---|
| earlier headline (n=96) | 22% template-seen | 99.0% | 90.6% |
| clean held-out (n=60) | **0%** | **90.0%** | **96.7%** |

## Results

60 held-out lines from the ten training systems — **0/60 exact and 0/60 template
overlap** with training, verified by `v3/measure_contamination.py`. Training drew
from Loghub-2.0; evaluation from Loghub-1.0, so the separation comes from how the
data was collected rather than a split I chose.

| arm | correct | accuracy | 95% CI |
|---|---|---|---|
| `rule_parser.py` (250 lines of regex) | 60/60 | **100.0%** | 94.0 – 100 |
| gemini-3.1-pro-preview | 58/60 | **96.7%** | 88.6 – 99.1 |
| **v3 (4B fine-tune)** | 54/60 | **90.0%** | 79.9 – 95.3 |

McNemar, v3 vs Gemini: 0 discordant pairs for v3, 4 for Gemini, **p = 0.125**.
Not significant at this sample size, but the direction is consistent.

**v3 does not beat Gemini.** It is within a few points at roughly 1/1000th the
marginal cost: Gemini bills **$0.011/line** (reasoning tokens included), where v3
runs free on a Colab T4. On abstention — `trace_id`, `status_code`, `latency_ms` —
all three arms were identical and none hallucinated.

One incidental finding: on the same trap in the same run, Gemini answered
correctly on one line and incorrectly on another with an identical template. v3
was consistently wrong; the parser consistently right. For a pipeline,
consistent-and-wrong is cheaper to fix than erratic.

## Why v3 lost — measured, not guessed

All six errors trace to three coverage gaps:

| errors | failure | measured cause |
|---|---|---|
| 3 | emitted the year from prose where the rule mandates a `1900` sentinel | **0** `ftpd` lines in training; the whole trap is 70 lines (0.65%) |
| 2 | `su(pam_unix)` → `pam_unix` instead of `su` | training has 4 process names with a qualifier — `sshd`, `gdm`, `login`, `passwd`. **`su` is absent** |
| 1 | Proxifier `[10.30 ...]` → month `03` | **1** Proxifier training example |

None is a failure to represent the rule. On `pam_unix(sshd:auth)` — the same rule
with a process name it *has* seen — v3 is correct. These are coverage gaps, and
`v3/PREREGISTRATION_V4.md` scopes the fix: ~800 targeted synthetic lines, one
retrain, with the acceptance criterion written before any number is seen.

## Cost

| item | |
|---|---|
| GPU — 4 training runs, RunPod RTX-2000-Ada class | ~$5.75 |
| Baseline API — Gemini via OpenRouter | ~$6.26 |
| P1 hand-labelling | ~$2.40 |
| **total** | **~$14.40** |

Inference cost is the point of the exercise: v3 is **$0/line** on a free T4
against Gemini's **$0.011/line** — about **$11 per 1000 lines** at frontier
pricing, versus nothing.

## What I would claim, and what I would not

**Claim:** on held-out logs from ten systems, with verified-zero template
overlap, a 4B fine-tune reaches 90% against a frontier model's 96.7% at zero
marginal inference cost, and the entire gap is attributable to three named
training-data gaps.

**Do not claim:** that it beats a frontier model, that the result is
statistically established (n=60, p=0.125), or that it generalises beyond these
ten formats. Out-of-distribution it degrades sharply — JSON, logfmt and Apache
combined logs appear **zero** times in training, and that is measured in
`real-eval/CONTAMINATION.md` rather than left to be discovered.

**Also worth stating plainly:** a 250-line deterministic parser beat both models.
On a distribution you fully control, hand-written rules remain the ceiling. The
fine-tune's argument is that it reaches 90% of that ceiling without anyone
hand-writing the rules — and that it parses lines the regex cannot touch at all
(19 of 20 on a non-Loghub corpus).

## Reproducing

One Colab notebook runs the whole evaluation on a free T4 — it proves the
train/eval split is clean *before* printing any accuracy number, then scores v3,
then takes log lines you paste in and puts v3, the parser and Gemini side by
side:

**https://colab.research.google.com/github/arshirazi97/tiny-log-parser/blob/main/heldout.ipynb**

Or locally:

```bash
git clone https://github.com/arshirazi97/tiny-log-parser && cd tiny-log-parser
git checkout v3-final
python3 v3/fetch_loghub1.py
python3 v3/measure_contamination.py          # verifies the split before any score
```

Every training line is committed (`v3/train_v3.jsonl`), raw sources are
SHA-256-pinned (`v3/SOURCES.txt`), and eval inputs are frozen
(`real-eval/EVAL_FREEZE_V4.txt`). `heldout.ipynb` runs the whole evaluation in
Colab, and takes your own logs.

## Tools

Log parsing and model evaluation are new to me, so I used AI assistance
throughout and want to be explicit about it. **Claude** was used for the
experimental design, the contamination methodology, the statistical analysis, and
the code and documentation in this repository — including finding the month-name
bug in my own contamination guard and identifying the three data gaps above.
**Gemini** served as the frontier baseline being measured against.

The design decisions, the pre-registrations, and the choice to report a negative
result rather than the contaminated 99.0% are mine. Everything here is
reproducible from the committed artifacts, which is the check that matters more
than who typed it.
