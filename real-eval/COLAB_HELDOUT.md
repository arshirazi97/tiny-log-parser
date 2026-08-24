# v3 on held-out in-distribution logs

The question: **how good is v3 on exactly the formats it was trained for, when
the specific lines are new?**

`messy.log` asked the opposite question — seven formats v3 has never seen, three
of which (`apache`, `logfmt`, `json`) appear **zero** times in its 10,728
training examples. This corpus is the other end: the same ten Loghub systems,
lines held out.

The pool is Loghub-**1.0** `<System>_2k.log`; v3 trained on Loghub-**2.0**. The
builder verifies the intersection is empty rather than assuming it, and also
excludes every line in `corpus_p1.jsonl`. It reported `excluded as
already-seen: 0`.

500 lines, 50 per system. `rule_parser.py` returns a parse on **500/500** —
compare 1/20 on `messy.log`. That is the definition of in-distribution.

**Runtime → Change runtime type → T4 GPU.** Three cells, ~5 min, $0.

## 1. setup (~3 min — restarts once, then re-run this same cell)

```python
import os
os.chdir('/content')
!rm -rf tiny-log-parser
!git clone -q https://github.com/arshirazi97/tiny-log-parser.git
os.chdir('/content/tiny-log-parser')
!pip install -q "transformers==4.51.3" "peft==0.20.0" accelerate bitsandbytes openai
!pip uninstall -q -y torchao      # peft 0.20 raises on torchao < 0.16

import importlib.util, transformers, peft
stale = ((transformers.__version__, peft.__version__) != ("4.51.3", "0.20.0")
         or importlib.util.find_spec("torchao") is not None)
if stale:
    print("restarting to pick up the new versions...")
    os.kill(os.getpid(), 9)
```

## 2. v3 on the held-out corpus (~2 min, mostly model load)

```python
import os
os.chdir('/content/tiny-log-parser')
!python real-eval/predict.py --arm model --adapter arshirazi/tiny-log-parser-v3 \
    --corpus real-eval/corpus_heldout.jsonl --batch 32 \
    --out real-eval/preds_heldout_v3.jsonl
```

Watch the `unparseable` count. On in-distribution formats it should be 0 — v3
emitted 1 unparseable in 262 lines on P1.

## 3. v3 against the rules reference

```python
!python real-eval/compare_arms.py --corpus real-eval/corpus_heldout.jsonl \
    --only-disagreements \
    rules=real-eval/preds_heldout_rules.jsonl v3=real-eval/preds_heldout_v3.jsonl
```

`preds_heldout_rules.jsonl` is committed, so the rules arm does not need
rerunning.

## Reading the result

**There are no gold labels here and none are invented.** The method is
adjudicated disagreement: diff the two arms, then hand-check only the lines
where they differ.

This is licensed by one specific fact and does not generalise: `rule_parser.py`
scored **100.0% (96/96)** on the P1 in-distribution slice, against independent
hand labels. It is a serviceable reference *on this distribution*. On
`messy.log` it is not a reference at all — it fails to parse 19 of 20.

So:

- **Agreement is the headline.** With rules at 100.0% on the P1 in-dist slice,
  v3-vs-rules agreement is a usable proxy for v3 accuracy here. It is a proxy,
  not a measurement — both arms can be wrong on the same line, and neither the
  proxy nor its error bar is a substitute for labels.
- **Every disagreement needs a human.** Rules being 96/96 on one sample does not
  make it right on line 497. Judge each against `schema_v2.SPEC_EVAL` and
  `ADJUDICATION.md`; expect a handful, and expect some to be rules' fault.
- **Watch `status_code`, `trace_id`, `latency_ms` in particular.** These are
  non-null in 1.79%, 3.17% and 2.97% of training. v3's learned prior is to
  abstain, which is right on this distribution and wrong off it. A disagreement
  here is the interesting one.

The prior expectation, for calibration: v3 scored **99.0% exact (95/96)** on the
P1 in-distribution slice — one `status_code` hallucination, perfect on the other
six fields. Gemini scored 90.6% on the same lines. If this 500-line run lands
far from ~99%, something is wrong with the run, not with v3.
