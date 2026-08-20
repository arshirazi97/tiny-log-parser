# Running the abstention probe (Colab, free T4)

Decides one question: **can the existing fine-tune emit `null` for `level` and
`service` at all?** If it cannot, it fails the sparse stratum (91 of 127 test
lines) by construction, and retraining is required before the real-log eval
measures anything.

Touches `corpus_dev.jsonl` only. The test corpus stays sealed.

---

**Prerequisite:** `real-eval/` must be pushed to the repo, or the clone below
won't contain the corpus. Alternatively use Colab's file uploader for
`corpus_dev.jsonl`.

**Runtime → Change runtime type → T4 GPU**, then run these two cells.

### Cell 1 — setup (~2 min)

```python
import os
os.chdir('/content')
!rm -rf tiny-log-parser
!git clone -q https://github.com/arshirazi97/tiny-log-parser.git
os.chdir('/content/tiny-log-parser')
!pip install -q "transformers==4.51.3" "peft==0.17.1" accelerate bitsandbytes

import transformers
if transformers.__version__ != "4.51.3":
    print("restarting to pick up new versions...")
    os.kill(os.getpid(), 9)
```

### Cell 2 — the probe (~4 min for 50 lines)

```python
import os
os.chdir('/content/tiny-log-parser')
!python real-eval/probe_abstention.py --corpus real-eval/corpus_dev.jsonl
```

### Cell 3 — optional: does prompt format matter?

The 100% was measured through the chat template (`run_local.py`), but `demo.py`
and the demo notebook use a flat prompt the model never saw in training. This
re-runs the same 50 lines the other way. If the two disagree, the demo path is
not the measured path and one of them needs to change.

```python
!python real-eval/probe_abstention.py --corpus real-eval/corpus_dev.jsonl \
    --prompt flat --out real-eval/probe_dev_flat.json

import json
a = json.load(open('real-eval/probe_dev.json'))
b = json.load(open('real-eval/probe_dev_flat.json'))
same = sum(x['pred'] == y['pred'] for x, y in zip(a['records'], b['records']))
print(f"identical predictions: {same}/{a['n']}")
print(f"unparseable  chat={a['unparseable']}  flat={b['unparseable']}")
```

---

## Reading the result

`null-rate per field` is the headline. If `level` and `service` are both **0%**,
the model never abstains — that is the measured justification for retraining,
and it is worth one line in the writeup.

`hallucination on lines with NO such token present` is the lower bound on the
hallucination rate. The detectors deliberately over-report presence, so the true
rate is at least this high.

Download `real-eval/probe_dev.json` before the runtime disconnects — it holds
every raw model output for inspection.
