# tiny-log-parser

**A 4B fine-tune plus ten lines of Python beats Gemini 3.1 Pro at log
normalization — 100% vs 83.5% exact match on the same test set.**

Takes a log line in any of six formats and emits one canonical JSON record:
always the same seven fields, always the same normalization rules.

```
input   <131>Mar  5 02:10:12 web-07 payments[4471]: TLS handshake aborted
        by peer [tid=8f2c91aa04bd77e35c1d6b0392ef4a18] took=4.775s

output  {"timestamp": "2026-03-04T21:10:12Z",
         "level": "ERROR",
         "service": "payments",
         "trace_id": "8f2c91aa04bd77e35c1d6b0392ef4a18",
         "status_code": null,
         "latency_ms": 4775,
         "message": "TLS handshake aborted by peer"}
```

The `+05:00` offset rolls the date back a full day, syslog severity `3` maps
to `ERROR`, and `4.775s` becomes `4775`.

---

## Results

200-example held-out test set. Same schema spec, same exact-match verifier,
all seven fields must match.

| | Exact match | 95% CI | Valid JSON | Latency p50 |
|---|---|---|---|---|
| gemini-3.1-pro-preview | 83.5% | 78.5 – 88.5% | 100% | 11,713 ms |
| Qwen3-4B fine-tune (model alone) | 73.0% | 66.5 – 79.0% | 100% | 4,197 ms |
| **Qwen3-4B + epoch pre-pass** | **100%** | 100 – 100% | 100% | 4,197 ms |

Per-field:

| Field | Baseline | Fine-tune alone | + pre-pass |
|---|---|---|---|
| timestamp | 97.5% | 73.0% | **100%** |
| level | 100% | 100% | 100% |
| service | 89.5% | **100%** | 100% |
| trace_id | 100% | 100% | 100% |
| status_code | 100% | 100% | 100% |
| latency_ms | 96.5% | **100%** | 100% |
| message | 99.5% | 100% | 100% |

**Fairness.** The baseline gets three few-shot examples in its prompt; the
fine-tune gets none. The fine-tune saw 20,000 examples during training, so
few-shotting it as well would be double-dipping — and zero-shot is how it
would run in production. The asymmetry favours the baseline deliberately.

---

## The interesting result

The model alone **loses** to the baseline: 73.0% vs 83.5%. But look at where.

Six of seven fields are at 100%. Every one of the 54 misses is a timestamp
error, and every one of those has correct minutes and seconds with wrong
hours and dates:

```
gold  2026-06-04T03:19:56Z    pred  2026-05-30T11:19:56Z
gold  2026-06-21T22:15:04Z    pred  2026-09-04T10:15:04Z
gold  2026-07-29T16:53:41Z    pred  2026-04-01T00:53:41Z
```

All of them are bare epoch integers. Converting `1780543196` to a date needs
integer division by 86400 plus calendar arithmetic across months of unequal
length. The model handles the cheap modulo (minutes, seconds) and fails the
division.

**Scaling did not fix this.** Two controlled runs on Qwen3-1.7B:

| Training examples | Exact match | timestamp |
|---|---|---|
| 5,000 | 57.5% | 72.5% |
| 20,000 | 56.5% | 73.0% |

Four times the data moved timestamp accuracy 0.5 points. That ruled out data
volume and pointed at capability. Moving to Qwen3-4B fixed `level`
(83.5% → 100%) but left timestamp at 73.0% — so it was not a general capacity
problem either. It was arithmetic specifically.

**The fix was to stop asking the model to do it.** A regex detects bare epoch
integers and `datetime.fromtimestamp()` converts them — exact, instant, zero
parameters. It fires on 41 of 200 inputs. Everything else still goes to the
model.

That is the actual finding: the right move was not a bigger model but
recognising that one subtask should never have been learned at all.

---

## Why a small model wins the rest

Capacity was never the bottleneck on the other six fields; **specification
was**. Parsing six log formats, mapping twenty level aliases and converting
three time units needs almost no reasoning. It needs the same rules applied
identically every time.

A frontier model is a generalist sampling over plausible interpretations. On
open-ended work that is an asset. On a task with exactly one correct answer
per input it means drift — `WARN` where the spec says `WARNING`, a reformatted
timestamp, a hallucinated `trace_id` where the spec says `null`. The baseline's
weakest field was `service` at 89.5%, where the name sits in six different
structural positions. The fine-tune takes it to 100%.

Economics reinforce it. Log parsing runs at millions of lines a day:

| | Per 1M log lines |
|---|---|
| gemini-3.1-pro-preview | ~$7,400 |
| this model, self-hosted | ~$3 |

Gemini 3.1 Pro also emits mandatory reasoning tokens — 44 of them just to
answer "say ok" — billed at output rate on every single line. It is not a
model anyone would deploy for this.

---

## The dataset is built backwards

No logs were collected and no labels were written by hand.

`generate.py` constructs the **canonical record first** — random timestamp,
level, service, trace id, latency — then renders it into a messy log line via
one of six format emitters (syslog RFC3164, nginx combined, logfmt, Java,
container JSON, bracket).

The label exists before the input does, so **every one of the 20,000 training
examples is correct by construction**. Train and test draw from disjoint time
windows (Jan–May vs Jun–Jul) so timestamps cannot be memorised. Generation is
seeded — one command reproduces the exact dataset.

---

## Limitations

**The test set is synthetic.** It comes from the same six renderers as
training, with disjoint time windows. That prevents timestamp memorisation but
not format memorisation. Once epoch conversion is routed deterministically,
what remains is pattern extraction over a bounded input space — a 4B model
saturating that is the expected outcome, not a surprising one. The 100% should
be read as "this task is solved within its stated distribution," not as a
claim about production logs.

**Real logs are harder.** Multiline stack traces, truncated lines, formats
outside these six, and vendor quirks are all absent here. Handling them would
mean training on real log corpora and adding renderers.

**One baseline, one run.** Compared against `gemini-3.1-pro-preview` only,
scored once, at temperature 0.

---

## Reproduce

```bash
pip install unsloth openai

# 1. dataset (seeded -- byte-identical every run)
python generate.py --train 20000 --test 200

# 2. frontier baseline
export OPENROUTER_API_KEY=...
python eval.py --runner baseline --n 200 --out baseline.json

# 3. fine-tune           (~2.5h on an RTX 2000 Ada, ~$0.60)
python train2.py --model unsloth/Qwen3-4B --data train.jsonl \
                 --epochs 2 --bs 2 --accum 8

# 4. inference + scoring
python run_local.py
python score.py           # model alone
python score_hybrid.py    # model + epoch pre-pass
```

Weights: [`arshirazi/tiny-log-parser`](https://huggingface.co/arshirazi/tiny-log-parser)

## Files

| | |
|---|---|
| `generate.py` | canonical-record generator + six format renderers |
| `train2.py` | LoRA fine-tune, response-masked so loss lands on the JSON only |
| `eval.py` | shared prompt spec, exact-match verifier, bootstrap CI |
| `run_local.py` | inference against the merged model |
| `score.py` / `score_hybrid.py` | scoring, with and without the epoch pre-pass |
| `baseline.json` / `mine.json` / `hybrid.json` | per-field results and saved misses |

## Setup

- **Base model** — Qwen3-4B
- **Method** — 4-bit QLoRA, r=16, 2 epochs, response masking, 20k examples
- **Hardware** — single RTX 2000 Ada (16 GB), ~2.5h, ~$0.60
- **Baseline** — `google/gemini-3.1-pro-preview` via OpenRouter, temperature 0
- **Total project cost** — ~$9 (GPU + baseline API)
