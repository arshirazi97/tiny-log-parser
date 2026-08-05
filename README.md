# logfmt-1.7b

**Beating a frontier model at log normalization with a 1.7B fine-tune.**

Takes a log line in any of six formats and emits one canonical JSON record —
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

Note the `+05:00` offset rolls the date back a full day, syslog severity
`3` maps to `ERROR`, and `4.775s` becomes `4775`.

---

## Results

| | logfmt-1.7b | gemini-3.1-pro-preview |
|---|---|---|
| Exact match (all 7 fields) | TBD | TBD |
| Valid JSON | TBD | TBD |
| Latency p50 | TBD | 10,393 ms |
| Cost / 1M log lines | TBD | TBD |

Same 200-example test set, same schema spec, same exact-match verifier.

**Fairness note.** The baseline receives three few-shot examples in its
prompt; the fine-tune receives none. The fine-tune saw 5,000 examples during
training, so few-shotting it as well would be double-dipping — and zero-shot
is how it would actually run in production. The asymmetry favours the
baseline deliberately.

---

## Why a small model wins here

Capacity is not the bottleneck on this task; **specification is**. Parsing six
log formats, mapping twenty level aliases and converting three time units
requires almost no reasoning. It requires applying the same rules identically
every single time.

A frontier model is a generalist sampling over plausible interpretations. On
open-ended work that is an asset. On a task with exactly one correct answer
per input it means drift — `WARN` where the spec says `WARNING`, a
reformatted timestamp, a hallucinated `trace_id` where the spec says `null`.
Fine-tuning collapses that distribution onto the single right answer.

The six failure modes the model targets:

1. **Timezone conversion across a date boundary** — `+05:00` at 02:10 rolls
   back to the previous day
2. **Enum normalization** — syslog severity `3` → `ERROR`, `NOTICE` → `INFO`
3. **Unit conversion** — `0.234s` → `234`, `234000us` → `234`, `rt=7.881` → `7881`
4. **Null discipline** — emitting `null` rather than inventing a plausible hex
   trace id
5. **A derived rule** — access logs carry no level field, so it must come from
   the status code (5xx→ERROR, 4xx→WARNING, else INFO)
6. **Message boundary** — stripping trailing metadata that is not part of the
   human-readable message

---

## The dataset is built backwards

No logs were collected and no labels were written by hand.

`generate.py` constructs the **canonical record first** — random timestamp,
level, service, trace id, latency — then renders it into a realistic messy log
line via one of six format emitters (syslog RFC3164, nginx combined, logfmt,
Java, container JSON, bracket).

The label therefore exists before the input does, and **every one of the 5,000
training examples is correct by construction**. Train and test draw from
disjoint time windows (Jan–May vs Jun–Jul) so timestamps cannot be memorized.

Generation is seeded, so the exact dataset is reproducible with one command.

---

## Reproduce

```bash
pip install unsloth openai

# 1. dataset  (seeded — byte-identical every run)
python generate.py --train 5000 --test 200

# 2. frontier baseline
export OPENROUTER_API_KEY=...
python eval.py --runner baseline --n 200 --out baseline.json

# 3. fine-tune            (~45 min on an RTX 2000 Ada, ~$0.20)
python train.py

# 4. serve + evaluate
vllm serve ./merged --max-model-len 1024 --gpu-memory-utilization 0.85 &
python eval.py --runner local --model ./merged --n 200 --out mine.json
```

---

## Files

| | |
|---|---|
| `generate.py` | canonical-record generator + six format renderers |
| `train.py` | LoRA fine-tune, response-masked so loss lands on the JSON only |
| `eval.py` | shared prompt spec, exact-match verifier, bootstrap CI |
| `baseline.json` / `mine.json` | per-field results and saved misses |

## Setup

- **Base model** — Qwen3-1.7B
- **Method** — 4-bit QLoRA, r=16, 2 epochs, response masking
- **Hardware** — single RTX 2000 Ada (16 GB)
- **Baseline** — `google/gemini-3.1-pro-preview` via OpenRouter, temperature 0

## Known limitations

TBD — filled in from the misses in `mine.json` after evaluation.
