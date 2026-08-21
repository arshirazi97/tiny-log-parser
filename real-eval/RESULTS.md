# Real-log evaluation — results

Scored 2026-08-21 against `labels_test.jsonl`, 127 lines from 10 LogHub
systems. One scoring pass, as designed. Reproduce with the commands at the
bottom; the prediction files are committed, so the tables below are checkable
without a GPU or an API key.

## Headline

| arm | exact (7 fields) | six-field | 95% CI (six) | unparseable |
|---|---|---|---|---|
| rules | 92.1% | 92.1% | 87.4 – 96.9% | 0 |
| Qwen3-4B fine-tune (v2) | 40.2% | 73.2% | 65.4 – 80.3% | 0 |
| **gemini-3.1-pro-preview** | **81.1%** | **96.1%** | 92.1 – 99.2% | 0 |

Sparse stratum only (91 lines, where most fields are absent and abstention is
the task): rules 89.0%, fine-tune 63.7%, Gemini 95.6%.

**McNemar, paired, exact, on six-field match:**

| comparison | discordant | p | winner |
|---|---|---|---|
| fine-tune vs Gemini | 0 – 29 | < 0.0001 | Gemini |
| rules vs fine-tune | 24 – 0 | < 0.0001 | rules |
| rules vs Gemini | 4 – 9 | 0.27 | not distinguishable |

**The fine-tune is not competitive on this corpus.** Zero wins across 29
discordant pairs is not a close result, and it does not become one under any
stratum split. The v1 claim that a 4B fine-tune beats a frontier model was an
artifact of scoring both on the fine-tune's own generative process; measured on
real logs it does not hold.

## Per-field accuracy

| field | rules | fine-tune | gemini |
|---|---|---|---|
| timestamp | 100.0% | 96.1% | 98.4% |
| level | 100.0% | 99.2% | 99.2% |
| service | 92.1% | 80.3% | 100.0% |
| trace_id | 100.0% | 100.0% | 100.0% |
| status_code | 100.0% | 99.2% | 99.2% |
| latency_ms | 100.0% | 92.1% | 98.4% |
| message | 100.0% | 54.3% | 85.0% |

## Hallucination — non-null emitted where the gold is null

| field | opportunities | rules | fine-tune | gemini |
|---|---|---|---|---|
| level | 53 | 0 | **1** | **1** |
| service | 9 | 0 | 0 | 0 |
| trace_id | 103 | 0 | 0 | 0 |
| status_code | 113 | 0 | 1 | 1 |
| latency_ms | 113 | 0 | 10 | 2 |

This is the result that survives. v1 emitted a non-null `level` on 50/50 dev
lines, including all 16 carrying no level token — a 100% hallucination rate
where abstention was required. v2 hallucinates a level on 1 of 53 opportunities
on the test set.

The one failure is shared: on

    [10.30 21:08:03] spoolsv.exe *64 - 127.0.0.1:135 error : Could not connect through proxy ...

both the fine-tune and Gemini emit `ERROR`, inferring a level from the word
"error" in the message body, which rule L3 excludes. The 4B model's only level
failure is one gemini-3.1-pro also makes.

The fine-tune's 10 latency hallucinations are one family: Proxifier
`lifetime 00:01` read as a latency, which rule F5 excludes. Gemini gets 8 of
those 10 right.

## What the S2c label correction cost each arm

`ADJUDICATION.md` S2c corrected 10 Proxifier `service` labels (`chrome.exe` →
`chrome.exe *64`) after `validate_labels_loghub.py` showed LogHub's independent
annotations keep the marker. Applied **before** any test scoring.

| arm | six-field (labels of record) | pre-correction | delta |
|---|---|---|---|
| rules | 92.1% | 100.0% | −7.9 |
| fine-tune | 73.2% | 77.2% | −3.9 |
| gemini | 96.1% | 89.0% | **+7.1** |

Reproduce with `--pre-s2c`. The correction cost both in-house arms and handed
the external baseline 7 points, which is the direction that makes it credible.
It also broke the rules arm's 100%-by-construction agreement with its own
author's labels — the condition `LABEL_REVIEW_TEST.md` named as necessary for
that arm to mean anything.

## Label independence

`validate_labels_loghub.py` scores the labels against LogHub's own
`*_2k.log_structured.csv` annotations — third-party, predating this project.

- **level: 127/127.** All 53 nulls fall in the four sources whose LogHub schema
  carries no usable level column.
- **service: 111/127.** The 16 remaining are two definitional families argued in
  `ADJUDICATION.md` (OpenSSH hostname-as-Component, Linux parenthesised
  qualifier).

The other five fields have no counterpart in their schema and remain
self-attested.

## Cost and latency

| | per line | per 1M lines | latency |
|---|---|---|---|
| gemini-3.1-pro-preview | $0.0159 | ~$15,900 | 8.8 s |
| Qwen3-4B fine-tune (T4) | ~$0.000003 | ~$3 | 4.2 s |
| rules | 0 | 0 | < 1 ms |

Gemini spent 1103 completion tokens per line — roughly 11× the JSON record it
emits — because reasoning tokens bill as completion. The accuracy gap is real;
so is a 5,000× cost gap.

## What this does and does not support

**Supported:** abstention is learnable per-field from nulls in the training
distribution; the v1 → v2 change was predicted in advance, and confirmed on real
logs against labels that are independently corroborated for `level`. A
deterministic parser is statistically indistinguishable from a frontier model
here (p = 0.27) at zero marginal cost.

**Not supported:** any claim that the fine-tune is competitive with a frontier
model at extraction on real logs. It is not, by a wide and significant margin.

**Still weak:** the rules arm and the labels share an author, so 92.1% is a
generous read of that arm even after S2c. n = 127 gives roughly ±8 points.
`message`, `timestamp` and `latency_ms` labels have no external corroboration.

## Reproduce

```bash
python real-eval/score_arms.py --labels real-eval/labels_test.jsonl \
    rules model=real-eval/preds_test_model.jsonl gemini=real-eval/preds_test_gemini.jsonl
python real-eval/score_arms.py --labels real-eval/labels_test.jsonl --stratum sparse rules \
    model=real-eval/preds_test_model.jsonl gemini=real-eval/preds_test_gemini.jsonl
python real-eval/score_arms.py --labels real-eval/labels_test.jsonl --pre-s2c rules \
    model=real-eval/preds_test_model.jsonl gemini=real-eval/preds_test_gemini.jsonl
python real-eval/validate_labels_loghub.py --labels real-eval/labels_test.jsonl
```
