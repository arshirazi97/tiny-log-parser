# Real-log eval: the fine-tune arm (Colab, free T4)

`predict.py --arm model` needs a CUDA GPU (the base is 4-bit). Everything else
in the eval -- the rules arm, the Gemini arm, `score_arms.py` -- runs on CPU
anywhere, so Colab is used for this one arm and the predictions are carried
back as files.

Order: smoke -> dev -> test. The test corpus is scored **once**; `predict.py`
refuses it without `--allow-test` for that reason.

**Runtime -> Change runtime type -> T4 GPU.**

---

### Cell 1 -- setup (~3 min)

```python
import os
os.chdir('/content')
!rm -rf tiny-log-parser
!git clone -q https://github.com/arshirazi97/tiny-log-parser.git
os.chdir('/content/tiny-log-parser')
!pip install -q "transformers==4.51.3" "peft==0.20.0" accelerate bitsandbytes
!pip uninstall -q -y torchao         # Colab ships 0.10.0; peft 0.20 raises under 0.16

import importlib.util, transformers, peft
stale = ((transformers.__version__, peft.__version__) != ("4.51.3", "0.20.0")
         or importlib.util.find_spec("torchao") is not None)
if stale:
    print("restarting to pick up the new versions...")
    os.kill(os.getpid(), 9)          # re-run this cell after the restart
```

`peft==0.20.0` matches the version that wrote `adapter_config.json`. Older peft
does load the adapter -- the `0.17.1` pin in `COLAB_PROBE.md` did, and the
committed notebook output records what it printed:

    UserWarning: Unexpected keyword arguments ['alora_invocation_tokens',
    'arrow_config', ... ] for class LoraConfig, these are ignored.

Ignored, not rejected. Nothing in that list changes LoRA maths today, so 0.17.1
would very likely give identical predictions -- but "very likely" is not a thing
to run a single-shot test-set eval through when the correct pin is free.

Uninstalling `torchao` is required, not tidying. `is_torchao_available()` in
peft 0.20 **raises** when torchao is importable and below 0.16.0, and Colab
preinstalls 0.10.0, so the load fails with

    ImportError: Found an incompatible version of torchao. Found version
    0.10.0, but only versions above 0.16.0 are supported

which reads like an adapter problem and is not one. With torchao absent the
check returns False and the load proceeds; quantization here is bitsandbytes.
Upgrading torchao instead would drag torch with it -- do not.

### Cell 2 -- smoke, 8 dev lines (~1 min)

```python
import os
os.chdir('/content/tiny-log-parser')
!python real-eval/predict.py --arm model --corpus real-eval/corpus_dev.jsonl --limit 8
```

Check before continuing: `spec=SPEC_EVAL (3084 chars)` -- not the frozen `SPEC`
-- and **0 unparseable**. Anything else and the test run is wasted GPU time.

### Cell 3 -- dev, 50 lines (~4 min)

```python
!python real-eval/predict.py --arm model --corpus real-eval/corpus_dev.jsonl
!python real-eval/score_arms.py --labels real-eval/labels_dev.jsonl rules model=real-eval/preds_dev_model.jsonl
```

Sanity check only, and it prints `PROVISIONAL` because the dev labels are still
`_review: pending`. The number to recognise is **~74% six-field** -- that is
where `probe_dev_v2.json` landed on the same 50 lines. Rules scoring 100% on
dev is circular (`LABEL_REVIEW_TEST.md`), not a result.

### Cell 4 -- the sealed test run, 127 lines (~10 min)

```python
!python real-eval/predict.py --arm model --corpus real-eval/corpus_test.jsonl --allow-test
```

Writes `real-eval/preds_test_model.jsonl`. Do not re-run it with different
decoding settings and keep the better one -- that spends the test set twice.

### Cell 5 -- get the files out before the runtime disconnects

```python
from google.colab import files
files.download('real-eval/preds_test_model.jsonl')
files.download('real-eval/preds_dev_model.jsonl')
```

Drop both into `real-eval/` locally and commit. The GPU's only job is done.

---

`demo.ipynb` sections 7-10 run these same commands as executable cells, with the
demo in front of them.

## Then the Gemini arm

Runs anywhere with an OpenRouter key; no GPU. One change is needed: the arm
takes its few-shot examples from `train_v2.jsonl`, which is gitignored, so the
clone does not have it.

```bash
export OPENROUTER_API_KEY=...
python generate_v2.py --train 200 --test 20      # seeded; the first 3 rows are
                                                 # byte-identical to the 20k run,
                                                 # so the shots are unchanged
python real-eval/predict.py --arm gemini --corpus real-eval/corpus_test.jsonl --allow-test
```

On Colab instead: `os.environ['OPENROUTER_API_KEY'] = userdata.get('OPENROUTER_API_KEY')`
via `from google.colab import userdata`.

Smoke it with `--limit 5` on the **dev** corpus first and confirm 0 unparseable
-- a wrong `--gemini-model` slug fails four times per line and silently writes
127 nulls.

## Scoring, once everything is in

```bash
python real-eval/score_arms.py --labels real-eval/labels_test.jsonl \
    rules model=real-eval/preds_test_model.jsonl \
          gemini=real-eval/preds_test_gemini.jsonl
```

The rules column is 100% by construction and is not a result. The comparison
that carries weight is **model vs gemini**, and the McNemar line under it.
