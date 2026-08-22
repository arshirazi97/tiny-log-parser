# tiny-log-parser

**Repo:** https://github.com/arshirazi97/tiny-log-parser
**Weights:** https://huggingface.co/arshirazi/tiny-log-parser-v2 (v1 kept at `arshirazi/tiny-log-parser`)
**Runnable demo (Colab, free T4):** https://colab.research.google.com/github/arshirazi97/tiny-log-parser/blob/main/demo.ipynb

---

## The task

Take a log line and emit one canonical JSON record with exactly seven fields:
`timestamp`, `level`, `service`, `trace_id`, `status_code`, `latency_ms`, `message`.

The same information sits in a different place in every format, with different level
vocabularies (`FATAL`, `err`, `W`, syslog severity `3`), different time units
(`4.775s`, `234000us`, `rt=1.500`), and different timezone conventions. On real logs
there is a second problem that matters more: **most fields are absent on most lines**,
and a system that cannot emit `null` fails them by construction.

## What v1 claimed, and why it is withdrawn

v1 reported **100% vs 83.5% exact match** against `gemini-3.1-pro-preview`, and that
number should not be used. `generate.py` produced the training set, the test set and
the scoring rubric. "Held-out" meant different rows from the same generative process,
so the comparison measured how well a fine-tune memorizes a rulebook against how well
a frontier model reads one once.

## The evaluation, rebuilt

**Independent inputs.** 127 test lines from ten real production systems (Loghub: HDFS,
OpenStack, OpenSSH, Linux, Hadoop, Spark, Zookeeper, Apache, HealthApp, Proxifier),
deduplicated by template signature, frozen by SHA-256, split from a 50-line dev set.
Nothing from the generator.

**Labels, stated exactly.** Drafted by a model from a written rule list
(`ADJUDICATION.md`) and reviewed — not hand-annotated from scratch. They are then
cross-checked against Loghub's own `*_2k.log_structured.csv` annotations, produced by
the logpai authors years earlier: **`level` agrees 127/127**, `service` 111/127. All 53
null levels fall in the four sources whose Loghub schema carries no level column.

**A correction that cost us.** That cross-check found 10 Proxifier labels that had
dropped the `*64` marker from `chrome.exe *64`. Corrected before any scoring: it cost
the rules arm 7.9 points and the fine-tune 3.9, and gave Gemini 7.1.

**Sealed.** `predict.py` refuses the test corpus without `--allow-test`. Scored once.

## Results

| arm | exact (7 fields) | six-field | 95% CI (six) | valid JSON |
|---|---|---|---|---|
| rules parser (250 lines of Python) | 92.1% | 92.1% | 87.4–96.9% | 100% |
| Qwen3-4B fine-tune (v2) | 40.2% | 73.2% | 65.4–80.3% | 100% |
| **gemini-3.1-pro-preview** | **81.1%** | **96.1%** | 92.1–99.2% | 100% |

McNemar's exact test, paired, on six-field match: **Gemini beats the fine-tune 29–0**
on discordant pairs, p < 0.0001. It does not recover under any split — on the 91 sparse
lines it is 63.7% against Gemini's 95.6%. Rules vs Gemini is 4–9, p = 0.27: unresolved
at this sample size, not a tie.

**The fine-tune is not competitive at extraction on real logs.** The baseline still
receives three few-shot examples and the fine-tune none, so every asymmetry points at
the baseline, and the baseline still wins.

## What survives: the model learned to abstain

A label-free probe found v1 emitting a **non-null `level` on 50 of 50** real dev lines,
including all 16 carrying no level token — a 100% hallucination rate where abstention
was required. The cause was in the data: all 20,000 v1 training examples had a level,
and abstention is learned per-field from nulls.

Predicted before the retrain: adding explicit nulls moves `level` to 70–90% abstention
with hallucination falling from 100%. Result: **34% abstention, 0/16 hallucinations** on
dev; **1 of 53** on the test set, and `trace_id` **0 of 103**. Undercorrected against the
prediction, and reported as such.

That single level failure is a Proxifier line containing the word "error" in its message
body. `gemini-3.1-pro` gets it wrong in exactly the same way.

## Why the fine-tune lost

It misses six-field on 34 of 127 lines, 42 field errors: `service` 25, `latency_ms` 10,
`timestamp` 5, `level` 1, `status_code` 1. Two families dominate:

- **Nested logger vs thread bracket.** Hadoop writes `[IPC Server handler 27 on 62270]
  org.apache.hadoop.mapred.TaskAttemptListenerImpl:`. The model takes the thread.
- **Duration is not latency.** Proxifier's `lifetime 00:01` is not the measured time of
  the logged event. The model reads it as `60000`.

**It was trained on 11 invented synthetic formats and tested on ten real systems it had
never seen.** Neither convention exists in any synthetic renderer. The evidence points at
a training-distribution gap rather than a capability limit — the same model learned
abstention from synthetic data and carried it to real logs cleanly — but that is an
explanation consistent with the results, not one this evaluation establishes.

## Cost

| | per line | per 1M lines | latency |
|---|---|---|---|
| gemini-3.1-pro-preview | $0.0159 | ~$15,900 | 8.8 s |
| Qwen3-4B fine-tune, self-hosted | ~$0.000003 | ~$3 | ~4.2 s |
| rules parser | 0 | 0 | < 1 ms |

Gemini spent **1,103 completion tokens per line** — roughly 11× the record it emits —
because reasoning tokens bill at output rate.

## What this does not show

**The rules arm shares an author with the labels**, so 92.1% is a generous read even
after the correction moved 10 labels off the parser. Only Gemini is independent of both
the labels and the training data.

**n = 127**, roughly ±8 points. **Only `level` and `service` are externally corroborated**;
the other five fields remain self-attested. **Single-line only** — no multi-line stack
traces, no formats outside these ten sources.

**The eval tests cross-system generalization from synthetic training**, which is harder
than the realistic deployment where a model is fine-tuned on the formats it will see.

## Use of AI assistance

I built this with Claude as a coding and research assistant. LLM fine-tuning and much of
the Python were new to me; my background is primarily frontend development.

Claude wrote most of the evaluation harness and **drafted the corpus labels** from my
rule list — which is why the labels are cross-checked against a third party's
annotations rather than presented as hand-annotated ground truth.

The decisions were mine: withdrawing the v1 result, sealing the test set, correcting
labels against my own arms' interest before scoring, and reporting a losing result
rather than tuning until it won.
