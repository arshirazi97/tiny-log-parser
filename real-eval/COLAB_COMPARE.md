# Messy-log head-to-head: v3 vs v2 vs Gemini (Colab, free T4)

A **side-by-side on unlabelled messy logs**, not a scored eval. `COLAB_EVAL.md`
documents the frozen, already-executed protocol on the labelled corpora and is
left alone; this is a separate path with a separate purpose.

## What this measures, and what it does not

There are no gold labels for `messy.log`. Nothing here produces an accuracy
number, and `score_arms.py` is deliberately not in the pipeline. What you get is
every line, every arm's six fields, and a mark on the fields where the arms
disagree. **Two arms agreeing can both be wrong.** A disagreement tells you only
that one of them is; read those lines yourself.

## Why this corpus is worth running

`messy.log` is 20 lines in seven shapes (syslog with a priority prefix, Apache
combined, logfmt, JSON, bracket-ISO, Java/logback, and one deliberately
truncated line) — none of them Loghub formats. `rule_parser.py` returns `None`
on **19 of 20**:

```
python real-eval/predict.py --arm rules --corpus real-eval/corpus_messy.jsonl
  -> 20 rows, 19 unparseable
```

That is the point. On the P1 corpus the parser is the ceiling and v3 is one line
short of it. Here the parser has no coverage at all, so this is the regime where
a model can actually be worth having — and the only question left is v3 vs
Gemini.

Run **v2 as well as v3**. v2 trained on `generate_v2.py` synthetic data, which
produces shapes like these; v3's mix moved to 75% real Loghub plus the two
targeted families. v3 may well be *worse* here than v2. That is a real
possibility and the reason to measure rather than assume.

**Runtime -> Change runtime type -> T4 GPU.**

---

### Cell 1 — setup (~3 min)

```python
import os
os.chdir('/content')
!rm -rf tiny-log-parser
!git clone -q https://github.com/arshirazi97/tiny-log-parser.git
os.chdir('/content/tiny-log-parser')
!pip install -q "transformers==4.51.3" "peft==0.20.0" accelerate bitsandbytes openai
!pip uninstall -q -y torchao         # required, not tidying -- see COLAB_EVAL.md

import importlib.util, transformers, peft
stale = ((transformers.__version__, peft.__version__) != ("4.51.3", "0.20.0")
         or importlib.util.find_spec("torchao") is not None)
if stale:
    print("restarting to pick up the new versions...")
    os.kill(os.getpid(), 9)          # re-run this cell after the restart
```

### Cell 2 — build the corpus

```python
import os
os.chdir('/content/tiny-log-parser')
!python real-eval/messy_corpus.py messy.log -o real-eval/corpus_messy.jsonl
!python real-eval/predict.py --arm rules --corpus real-eval/corpus_messy.jsonl \
        --out real-eval/preds_messy_rules.jsonl
```

To use your own lines instead, write them to a file first — one log line per
line, no labels needed:

```python
open('mine.log','w').write("""<paste your log lines here>""")
!python real-eval/messy_corpus.py mine.log -o real-eval/corpus_messy.jsonl
```

### Cell 3 — smoke, 3 lines (~1 min)

```python
!python real-eval/predict.py --arm model --adapter arshirazi/tiny-log-parser-v3 \
        --corpus real-eval/corpus_messy.jsonl --limit 3 --out /tmp/smoke.jsonl
!cat /tmp/smoke.jsonl
```

Confirm `spec=SPEC_EVAL` and **0 unparseable** before spending time on the rest.

### Cell 4 — v3 (~2 min)

```python
!python real-eval/predict.py --arm model --adapter arshirazi/tiny-log-parser-v3 \
        --corpus real-eval/corpus_messy.jsonl --batch 32 \
        --out real-eval/preds_messy_v3.jsonl
```

### Cell 5 — v2, same base, different adapter (~2 min)

```python
!python real-eval/predict.py --arm model --adapter arshirazi/tiny-log-parser-v2 \
        --corpus real-eval/corpus_messy.jsonl --batch 32 \
        --out real-eval/preds_messy_v2.jsonl
```

### Cell 6 — Gemini (~1 min, ~$0.02 for 20 lines)

```python
from google.colab import userdata
import os
os.environ['OPENROUTER_API_KEY'] = userdata.get('OPENROUTER_API_KEY')

!python real-eval/predict.py --arm gemini --shots 0 \
        --corpus real-eval/corpus_messy.jsonl \
        --out real-eval/preds_messy_gemini.jsonl
```

`--shots 0` on purpose. The labelled eval gives Gemini three few-shot examples
as a deliberate handicap against an untrained baseline; here both arms should
get the identical prompt — `SPEC_EVAL` and nothing else — so a difference is a
difference in the model. It also avoids depending on `train_v2.jsonl`, which is
gitignored and absent from the clone.

Smoke it with `--limit 3` first: a wrong `--gemini-model` slug retries four
times per line and silently writes nulls.

### Cell 7 — the comparison

```python
!python real-eval/compare_arms.py --corpus real-eval/corpus_messy.jsonl \
        v3=real-eval/preds_messy_v3.jsonl \
        v2=real-eval/preds_messy_v2.jsonl \
        gemini=real-eval/preds_messy_gemini.jsonl
```

Add `--only-disagreements` to skip the lines all three agree on. The tail prints
per-field agreement, how many lines are identical across all arms, and a
non-null count per field — that last table is where over-extraction shows up, so
watch `latency_ms` and `status_code`, the two fields v2 invented most.

### Cell 8 — get the files out before the runtime disconnects

```python
from google.colab import files
for f in ("v3", "v2", "gemini", "rules"):
    files.download(f'real-eval/preds_messy_{f}.jsonl')
```

---

## Reading the result

Judge these by hand, against the schema, not by which arm looks confident:

- **`level` on lines that carry none.** `Error -60005 creating authorization`
  has no level field; `ERROR` is prose. v2 held 0/32 on gold-null in the
  labelled eval and v3 held it too — check it survives here.
- **`latency_ms` vs a duration in prose.** `took=4.775s` and `rt=7.881` are
  structural; `finished in 6.049 s` is not. This is the F2 family v3 was
  trained on, on formats it has not seen.
- **`service` on the truncated line** (`<134>Jul 12 18:44:0`). There is no
  service token. Anything non-null is invention.
- **`timestamp` with no year.** The schema says a `1900` sentinel, not a guess
  at the current year — and several of these lines carry a real year, so both
  behaviours should appear.

If v3 and Gemini disagree on a line, decide which is right by reading
`schema_v2.SPEC_EVAL`, then record it. Twenty hand-adjudicated messy lines is a
small labelled corpus, and it is worth more than the agreement percentage.
