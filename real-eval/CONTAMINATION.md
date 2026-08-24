# Train/eval separation

> "The fine-tuned LLM cannot be benchmarked on the exact dataset it was trained
> with. Means essentially nothing."

The objection is correct in general, and **zero exact-line overlap is not a
reply to it.** A log corpus is a few hundred templates instantiated thousands of
times; two lines can share a template, differ in every number, and never collide
as strings.

v3 anticipated this. `PREREGISTRATION.md` declared contamination control at
*signature* level before the run, and `build_train_v3.py` enforces it with a
hard abort — "verify, do not assume", in the code. So the generic form of the
objection does not land: v3 was not benchmarked on its training set, and that
was established in advance rather than argued afterwards.

One narrower version of the objection did land. It is recorded below.

```bash
python3 v3/measure_contamination.py
```

## The month-name gap

`build_corpus.signature()` masked digits, IPs, hex and paths — but not textual
month names. So these two signed differently and crossed the train/eval boundary
undetected:

```
EVAL   [Thu Jun 09 06:07:19 2005] [notice] Digest: done
TRAIN  [Thu Jan 26 12:23:07 2006] [notice] Digest: done
```

A month is timestamp *content*, not template structure; Loghub's own
`EventTemplate` treats these as one event. The gap affected every format with a
textual month — Linux, OpenSSH, Apache.

Fixed in `build_corpus.py`: a month is masked when followed by a day number, so
`May` in prose and a service named `Mar` are left alone. The signature is now
imported by `measure_contamination.py` rather than copied, so the guard and the
measurement cannot drift apart again.

**Detected leakage after the fix: 59 eval lines that the old signature passed** —
35/262 in `corpus_p1.jsonl`, 21/96 in `labels_p1.jsonl`, 2/42 in
`corpus_p1_unseen42.jsonl`, and 1/127 in the sealed `corpus_test.jsonl`.

## What the eval sets contain

`train_v3.jsonl` is 10,728 lines / 4,576 distinct templates. Against it:

| eval set | exact | same template | J ≥ 0.90 | median max-J |
|---|---|---|---|---|
| `labels_p1.jsonl` | 0/96 | **21/96 (22%)** | 30/96 | **0.79** |
| `corpus_p1_unseen42.jsonl` | 0/42 | 2/42 (5%) | 3/42 | 0.43 |
| `corpus_heldout.jsonl` | 0/500 | **0/500** | 11/500 | 0.36 |
| `messy.log` | 0/20 | 0/20 | 0/20 | 0.19 |

`J` is token Jaccard against *every* training template, so a line that merely
resembles one is still caught.

**The 99.0% figure from `labels_p1.jsonl` must not be quoted as clean held-out
accuracy** — 22% of that set shares a template with training.

`corpus_heldout.jsonl` is clean under both the project signature and a stricter
independent one. 500 lines, ten systems, drawn from Loghub-1.0 against training
drawn from Loghub-2.0 — a split that comes from how the data was collected, not
from a partition anyone chose.

## Does familiarity buy v3 anything?

Exposure bounds the risk; it cannot say whether it mattered. A reciting model
scores well on templates it has seen and falls over on ones it has not:

| tier | n | v3 exact | 95% CI | rules |
|---|---|---|---|---|
| seen (J ≥ 0.90) | 30 | 100.0% | 88.6 – 100 | 100.0% |
| similar (0.50–0.90) | 38 | 100.0% | 90.8 – 100 | 100.0% |
| unseen (J < 0.50) | 28 | 96.4% | 82.3 – 99.4 | 100.0% |

Fisher exact, seen vs unseen: **p = 0.483**. The whole gap is one line.

**This is weak evidence and should be presented as weak.** At n = 28 the unseen
tier would have to fall to 24/28 (85.7%) before the difference reached
significance. The result is consistent with no memorisation effect; it does not
establish that one is absent.

## What to claim

- **Do not defend the 99.0%.** It is 22% template-contaminated. Concede it.
- **`corpus_heldout.jsonl` is the honest answer** — 0/500 under either
  signature. It has not been run; v3 needs a GPU. See `COLAB_HELDOUT.md`.
- Even a spotless run there says only that **v3 generalises to new lines in the
  ten formats it was trained on**. That is in-distribution generalisation and
  should be labelled as such, not as "unseen data".

The out-of-distribution answer is worse and separate. `messy.log` sits at median
J = 0.19, and three of its seven shapes — `apache`, `logfmt`, `json` — occur
zero times in training, as do nine of its ten distinguishing features. The field
priors invert too: `latency_ms` is non-null in 2.97% of training and 85% of
`messy.log`. Every non-null latency v3 has seen came from one synthetic family
in one notation, `time: <n>`; `messy.log` uses six others and none is that one.
