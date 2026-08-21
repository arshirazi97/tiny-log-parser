# tiny-log-parser

**A 4B fine-tune, a deterministic parser, and Gemini 3.1 Pro, measured on 127
adjudicated lines of real production logs. The fine-tune loses. The 250-line
parser doesn't.**

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/arshirazi97/tiny-log-parser/blob/main/demo.ipynb)

Takes a log line and emits one canonical JSON record: always the same seven
fields, always the same normalization rules, and `null` for every field the line
does not carry.

```
input   Dec 10 07:11:42 LabSZ sshd[24224]: pam_unix(sshd:auth): authentication
        failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=202.100.179.208

output  {"timestamp": "1900-12-10T07:11:42Z",
         "level": null,
         "service": "sshd",
         "trace_id": null,
         "status_code": null,
         "latency_ms": null,
         "message": "authentication failure; logname= uid=0 ..."}
```

Four of seven fields are `null`, and that is the hard part. `authentication
failure` is not an `ERROR` — the line carries no level, and inventing one
poisons every downstream alert built on the field. The year is absent, so a
`1900` sentinel says so rather than guessing.

---

## Results

127 lines from ten real production systems (Loghub: HDFS, OpenStack, OpenSSH,
Linux, Hadoop, Spark, Zookeeper, Apache, HealthApp, Proxifier), deduplicated by
template signature, frozen by hash, labelled against a written rule list and
cross-checked against Loghub's own annotations, **scored once**. Full detail in [`real-eval/RESULTS.md`](real-eval/RESULTS.md).

| arm | exact (7 fields) | six-field | 95% CI (six) | valid JSON |
|---|---|---|---|---|
| rules (`rule_parser.py`) | 92.1% | 92.1% | 87.4 – 96.9% | 100% |
| Qwen3-4B fine-tune (v2) | 40.2% | 73.2% | 65.4 – 80.3% | 100% |
| **gemini-3.1-pro-preview** | **81.1%** | **96.1%** | 92.1 – 99.2% | 100% |

Six-field excludes `message`, the most judgement-dependent field, so a
formatting quibble does not swamp the extraction result.

**McNemar's exact test, paired, on six-field match:**

| comparison | discordant pairs | p | result |
|---|---|---|---|
| fine-tune vs Gemini | 0 – 29 | < 0.0001 | Gemini |
| rules vs fine-tune | 24 – 0 | < 0.0001 | rules |
| rules vs Gemini | 4 – 9 | 0.27 | indistinguishable |

**The fine-tune is not competitive at extraction on real logs.** Zero wins in 29
discordant pairs, and it does not improve under any stratum split — on the 91
sparse lines it drops to 63.7% against Gemini's 95.6%.

An earlier version of this README claimed the opposite, on a test set drawn from
the same generator as the training data. That claim is withdrawn; see
[Appendix](#appendix--the-synthetic-result-and-what-it-was-worth).

**Fairness.** The baseline gets three few-shot examples; the fine-tune gets none.
Both receive identical spec text. Every asymmetry points at the baseline
deliberately, and the baseline still wins.

---

## What does survive: the model learned to abstain

Most real log lines carry three or four of the seven fields. A system that
cannot emit `null` fails them by construction, and v1 could not.

A label-free probe on 50 real lines found v1 emitting a **non-null `level` on
50 of 50**, including all 16 that contain no level token at all — a 100%
hallucination rate where abstention was required — while correctly abstaining on
`trace_id` (82%), `status_code` (90%) and `latency_ms` (82%).

The diagnosis was in the training data, not the weights: all 20,000 v1 examples
carried a level and a service, and **abstention is learned per-field from nulls
in the data**. The three fields that had nulls in training were the three it
could abstain on.

The prediction, registered before the retrain: add explicit nulls and `level`
moves to 70–90% abstention with hallucination falling from 100%.

| | v1 | v2 |
|---|---|---|
| `level` abstention (dev) | 0% | 34% |
| `level` hallucination where no level token present | 100% (16/16) | **0%** (0/16) |

Undercorrected against the prediction, but the direction held and the
hallucination rate went to zero. On the test set the fine-tune hallucinates a
level on **1 of 53** opportunities, and `trace_id` on **0 of 103**.

That single level failure is worth reading:

```
[10.30 21:08:03] spoolsv.exe *64 - 127.0.0.1:135 error : Could not connect ...
```

Both the fine-tune and gemini-3.1-pro emit `ERROR` here, inferring a level from
the word "error" in the message body, which the rule list excludes. The 4B
model's only level failure is one the frontier model also makes.

---

## How the evaluation is built

The v1 evaluation scored a fine-tune on the output of the generator it was
trained on. That measures memorization of a rulebook, not extraction. This one is
built so it cannot do that.

**Independent inputs.** `build_corpus.py` pulls Loghub's raw `_2k.log` files,
deduplicates by template signature so the sample is distinct log *shapes* rather
than 40 copies of one line, stratifies into rich and sparse, and splits dev (50,
iterate freely) from test (127, touch once). Hashes in `CORPUS_FREEZE.txt`.

**Independently corroborated labels.** The labels were drafted by a model from
the written rule list in `ADJUDICATION.md` and reviewed — not hand-annotated from
scratch, and `LABEL_REVIEW_TEST.md` says so exactly. `validate_labels_loghub.py`
then scores them against Loghub's own `*_2k.log_structured.csv` annotations,
produced by the logpai authors years before this project:

- **`level`: 127/127.** All 53 null levels fall in the four sources whose Loghub
  schema carries no usable level column. An independent party asserts there is
  no level to extract in exactly the lines labelled `null`.
- **`service`: 111/127**, the remainder two definitional families argued in
  `ADJUDICATION.md`.

**A label correction that cost us.** That cross-check found 10 Proxifier labels
that had dropped the `*64` marker from `chrome.exe *64`. Corrected before any
test scoring:

| arm | six-field (labels of record) | pre-correction | delta |
|---|---|---|---|
| rules | 92.1% | 100.0% | −7.9 |
| fine-tune | 73.2% | 77.2% | −3.9 |
| gemini | 96.1% | 89.0% | **+7.1** |

Reproduce with `score_arms.py --pre-s2c`. It cost both in-house arms and gave the
external baseline seven points — and it broke the rules arm's 100%-by-construction
agreement with its own author's labels.

**A sealed test set.** `predict.py` refuses the test corpus without
`--allow-test`. Dev is where the iteration happened; test was scored in one pass,
after both arms' predictions existed.

---

## Where the fine-tune actually fails

It misses six-field on 34 of 127 lines, 42 field errors in total: `service` 25,
`latency_ms` 10, `timestamp` 5, `level` 1, `status_code` 1. Gemini misses 5 lines
and 6 fields. The two dominant families are conventions rather than capability:

- **Nested logger vs thread bracket.** Hadoop writes
  `[IPC Server handler 27 on 62270] org.apache.hadoop.mapred.TaskAttemptListenerImpl:`.
  The logger is the class; the model takes the thread. Loghub's own schema splits
  these into separate columns, agreeing with the rule list.
- **Duration is not latency.** Proxifier's `lifetime 00:01` is how long a
  connection lived, not the measured time of the logged event. The model reads it
  as `60000`. Six of its ten `latency_ms` errors are this pattern, and Gemini is
  correct on 8 of the 10 lines where the fine-tune gets the field wrong.

Both rules are stated in the spec both systems receive. The fine-tune reads them
and still misapplies them; that is a training-distribution gap, and the fix is
training data containing those conventions, not a larger model.

---

## Cost

| | per line | per 1M lines | latency |
|---|---|---|---|
| gemini-3.1-pro-preview | $0.0159 | ~$15,900 | 8.8 s |
| Qwen3-4B fine-tune, self-hosted | ~$0.000003 | ~$3 | ~4.2 s\* |
| rules | 0 | 0 | < 1 ms |

Measured over the 127-line test run: Gemini spent **1,103 completion tokens per
line** — roughly 11× the JSON record it emits — because reasoning tokens bill at
output rate on every line.

The accuracy gap is real and significant. So is a 5,000× cost gap, and a
deterministic parser that a frontier model cannot be distinguished from at
p = 0.27.

\* carried from the v1 synthetic run; the real-log run was batched and not timed
per line.

---

## Appendix — the synthetic result, and what it was worth

The original result was **100% vs 83.5% exact match** against
`gemini-3.1-pro-preview` on a 200-example held-out set, with a deterministic
epoch pre-pass on top of the fine-tune.

**It is withdrawn as evidence of extraction quality.** `generate.py` produced the
training set, the test set and the scoring rubric. "Held-out" meant different
rows from the same process, so the comparison measured how well a fine-tune
memorizes a rulebook against how well a frontier model reads one once.

One finding from that work does survive, because it does not depend on the test
set being independent:

**The model could not do epoch arithmetic, and more data did not help.** Every
timestamp miss had correct minutes and seconds with wrong hours and dates — all
of them bare epoch integers, where `1780543196` needs integer division by 86400
plus calendar arithmetic. Two controlled runs on Qwen3-1.7B:

| Training examples | Exact match | timestamp |
|---|---|---|
| 5,000 | 57.5% | 72.5% |
| 20,000 | 56.5% | 73.0% |

Four times the data moved timestamp accuracy 0.5 points. Moving to Qwen3-4B
fixed `level` but left timestamp at 73.0%, so it was not general capacity
either. The fix was to stop asking: a regex detects bare epochs and
`datetime.fromtimestamp()` converts them, exactly, on 41 of 200 inputs.

The right move was not a bigger model but recognising that one subtask should
never have been learned at all. That still holds.

---

## Limitations

**The rules arm shares an author with the labels.** Both trace to the same rule
list, so 92.1% is a generous read of that arm even after the S2c correction moved
10 labels away from it. Only the Gemini arm is fully independent of both the
labels and the training data.

**n = 127.** Roughly ±8 points on the six-field numbers. The rules-vs-Gemini
comparison is genuinely unresolved at this sample size, not a tie.

**Only `level` and `service` are externally corroborated.** `timestamp`,
`latency_ms`, `trace_id`, `status_code` and `message` labels have no counterpart
in Loghub's schema and remain self-attested.

**Single-line only.** Multi-line stack traces, truncated lines and formats
outside these ten sources are absent. The schema's seven fields are also the
wrong abstraction for some sources entirely.

**One baseline, one run**, at temperature 0.

---

## Reproduce

The prediction files are committed, so the scoring tables need no GPU and no API
key:

```bash
python real-eval/score_arms.py --labels real-eval/labels_test.jsonl \
    rules model=real-eval/preds_test_model.jsonl gemini=real-eval/preds_test_gemini.jsonl
python real-eval/validate_labels_loghub.py --labels real-eval/labels_test.jsonl
```

From scratch:

```bash
# 1. corpus (seeded; hashes in CORPUS_FREEZE.txt)
python real-eval/build_corpus.py --out real-eval

# 2. training data + fine-tune  (~2.5h on an RTX 2000 Ada, ~$0.60)
python generate_v2.py --train 20000 --test 200
python validate_v2.py train_v2.jsonl test_v2.jsonl     # must print PASS
python train2.py --model unsloth/Qwen3-4B --data train_v2.jsonl \
                 --spec v2 --epochs 2 --bs 2 --accum 8

# 3. the arms (the model arm needs a GPU; see real-eval/COLAB_EVAL.md)
python real-eval/predict.py --arm model  --corpus real-eval/corpus_test.jsonl --allow-test
export OPENROUTER_API_KEY=...
python real-eval/predict.py --arm gemini --corpus real-eval/corpus_test.jsonl --allow-test
```

Weights: [`arshirazi/tiny-log-parser-v2`](https://huggingface.co/arshirazi/tiny-log-parser-v2)
(v1 kept at [`arshirazi/tiny-log-parser`](https://huggingface.co/arshirazi/tiny-log-parser)
so the abstention comparison stays reproducible).

## Files

| | |
|---|---|
| `real-eval/build_corpus.py` | Loghub fetch, template dedup, stratify, freeze |
| `real-eval/ADJUDICATION.md` | the labelling rule list, including corrections |
| `real-eval/validate_labels_loghub.py` | labels vs Loghub's own annotations |
| `real-eval/predict.py` | run one arm (rules / model / gemini) over a corpus |
| `real-eval/score_arms.py` | scoring, bootstrap CIs, McNemar, `--pre-s2c` |
| `real-eval/probe_abstention.py` | label-free abstention probe (the v1 diagnosis) |
| `real-eval/RESULTS.md` | the scored tables and what they do not support |
| `generate_v2.py` / `schema_v2.py` | canonical-record generator, with nulls |
| `train2.py` | LoRA fine-tune, response-masked so loss lands on the JSON only |
| `generate.py` / `eval.py` / `score*.py` | the v1 synthetic pipeline (appendix) |

## Setup

- **Base model** — Qwen3-4B
- **Method** — 4-bit QLoRA, r=16, 2 epochs, response masking, 20k examples
- **Hardware** — single RTX 2000 Ada (16 GB), ~2.5h, ~$0.60
- **Baseline** — `google/gemini-3.1-pro-preview` via OpenRouter, temperature 0
- **Evaluation** — 127 real log lines, scored once, $2.02 of baseline API
