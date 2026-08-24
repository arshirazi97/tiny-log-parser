# Held-out results — the clean-corpus numbers

"A fine-tuned model cannot be benchmarked on the dataset it was trained on."
That objection is correct, and acting on it cost this project its headline
number. What follows is what the results look like once the eval corpora are
verified clean.

## What we trained

Qwen3-4B, 4-bit + LoRA. 10,728 examples: 8,046 real Loghub lines from ten
systems (Spark, Linux, Hadoop, HDFS, Apache, Zookeeper, HealthApp, OpenSSH,
OpenStack, Proxifier) and 2,682 synthetic lines targeting four specific
adjudication rules. Task is seven-field extraction — timestamp, level, service,
trace_id, status_code, latency_ms, message.

## How we checked separation

Contamination control was pre-registered and enforced in code — the training
builder aborts if any eval line's template signature appears in training.

It had a bug. The signature masked digits, IPs, hex and paths, but not
textual month names. So these signed differently and crossed the boundary:

```
EVAL   [Thu Jun 09 06:07:19 2005] [notice] Digest: done
TRAIN  [Thu Jan 26 12:23:07 2006] [notice] Digest: done
```

Fixed. Re-checking every corpus found **59 eval lines the old guard passed**,
including one in the sealed test set. The headline eval set turned out to be
**22% template-contaminated**.

## What that did to the result

| corpus | contamination | v3 | gemini-3.1-pro | rules |
|---|---|---|---|---|
| `labels_p1` (n=96) | 22% | **99.0%** | 90.6% | 100% |
| `heldout50` (n=50) | **0%** | **92.0%** | **98.0%** | 100% |

A 15-point swing when the contamination is removed. Every discordant pair (0–3)
favours Gemini. McNemar p = 0.25 — not significant at n=50, but the direction is
against the fine-tune.

One confound: the clean corpus is also stratified 5-per-system, which
over-weights the weakest systems (Proxifier is 10% here vs 1% before). So the whole swing cannot be attributed to contamination. On this corpus v3 loses
either way.

## What broke, specifically

Both failures were training-data gaps, not capability:

- `su(pam_unix)` → training has 49 `X(pam_unix)` lines (`gdm`, `login`, `sshd`) and
  **zero** `su`. Gemini applied the rule to an unseen process name; v3 couldn't.
- Proxifier `[10.30 ...]` → **one** training example. Not enough to learn
  `MM.DD` order.

## Where we actually stand

Not "beats Gemini." On the cleanest evidence available, it does not.

What holds: a 4B fine-tune at 92% against a frontier model's 98% —
statistically indistinguishable at this sample size — at **zero marginal cost on
a free T4**, versus ~$2.96 per 1000 lines. The value is the ratio, not the
ranking.

Also worth noting: the 250-line deterministic parser scored 50/50, beating both.
On a distribution you fully control, hand-written rules are still the ceiling.

## Next

- Run the clean 500-line corpus (n=50 settles nothing at p=0.25)
- Close the two data gaps
- Everything is reproducible: `python3 v3/measure_contamination.py` verifies the
  split before any accuracy number is computed.

See `CONTAMINATION.md` for the full separation audit.
