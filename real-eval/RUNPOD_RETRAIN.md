# v2 retrain on RunPod

Trains the abstention-capable model. ~2.5h, ~$0.60 at RTX-2000-Ada-class pricing.

## Pod

- **GPU**: 16 GB or more. Anything in the A4000 / A5000 / L4 / 4090 class works;
  pick the cheapest that fits.
- **Template**: a PyTorch 2.x image.
- **Container disk: 50 GB.** This is the usual RunPod failure. The 4-bit base is
  ~3.5 GB, the HF cache holds another copy, and `save_pretrained_merged` writes
  an ~8 GB fp16 model on top. The default disk is not enough.

If disk is tight, you can skip the merged save entirely -- see "Disk" below.

## Run

```bash
git clone https://github.com/arshirazi97/tiny-log-parser.git
cd tiny-log-parser
pip install -q unsloth

# 1. dataset (seeded; byte-identical every run)
python generate_v2.py --train 20000 --test 200

# 2. never train on data that has not passed this
python validate_v2.py train_v2.jsonl test_v2.jsonl     # must print PASS

# 3. smoke test first -- minutes, not hours
head -200 train_v2.jsonl > smoke_v2.jsonl
python train2.py --model unsloth/Qwen3-4B --data smoke_v2.jsonl \
                 --spec v2 --epochs 1 --bs 2 --accum 8
```

Check two things in the smoke output before continuing:

- `spec: v2  (2338 chars)`
- the `--- loss is computed on ---` block shows **only** the JSON record.
  If prompt text appears there, response masking is broken -- stop.

```bash
# 4. the real run, ~2.5h
python train2.py --model unsloth/Qwen3-4B --data train_v2.jsonl \
                 --spec v2 --epochs 2 --bs 2 --accum 8
```

## Push before you terminate

The pod is ephemeral. `./lora_adapter` is 132 MB and is all the real-log eval
needs -- the probe applies it to the base itself.

Push to a **new repo**, not over `arshirazi/tiny-log-parser`. Keeping v1 intact
is what makes the v1-vs-v2 abstention comparison meaningful.

```bash
huggingface-cli login
huggingface-cli upload arshirazi/tiny-log-parser-v2 ./lora_adapter
```

## Then probe it

Back on Colab (a T4 is fine for inference):

```bash
python real-eval/probe_abstention.py --corpus real-eval/corpus_dev.jsonl \
    --adapter arshirazi/tiny-log-parser-v2 --out real-eval/probe_dev_v2.json
```

**The prediction being tested:** `level` and `service` move from 0% null to
roughly 70-90%, where `trace_id` (82%), `status_code` (90%) and `latency_ms`
(82%) already sit, and the level hallucination rate falls from 100%.

If that holds, it is hypothesis -> intervention -> confirmation on real logs
from a completely different generative process than the training data.

## Disk

`train2.py` saves `./lora_adapter` (132 MB) and then `./merged` (~8 GB fp16).
Only the adapter is needed for the probe and for the real-log eval. If the pod
runs out of disk on the merged save, the adapter has already been written -- push
it and move on. `./merged` only matters for `run_local.py`, which scores the
synthetic set, and that is now an appendix.
