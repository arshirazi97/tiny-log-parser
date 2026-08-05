"""
LoRA fine-tune Qwen3-1.7B for log normalization.

No TRL, no datasets.map -- plain PyTorch loop. Nothing to pickle.

    python train2.py                    # 5000 examples, 2 epochs
    python train2.py --data tiny.jsonl --epochs 1    # smoke test
"""

import argparse
import json
import math

import torch
from torch.utils.data import DataLoader, Dataset
from unsloth import FastLanguageModel

from eval import SPEC


def build_messages(raw, target=None):
    """Single source of truth for prompt format. eval.py imports this."""
    msgs = [
        {"role": "system", "content": SPEC},
        {"role": "user", "content": raw},
    ]
    if target is not None:
        msgs.append({"role": "assistant", "content": json.dumps(target)})
    return msgs


class LogDataset(Dataset):
    """Pre-tokenized. Labels masked so loss lands only on the JSON."""

    def __init__(self, rows, tok, max_len):
        self.items = []
        for r in rows:
            prompt = tok.apply_chat_template(
                build_messages(r["input"]),
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            full = prompt + json.dumps(r["output"]) + "<|im_end|>"

            p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
            f_ids = tok(full, add_special_tokens=False)["input_ids"][:max_len]

            labels = list(f_ids)
            for i in range(min(len(p_ids), len(labels))):
                labels[i] = -100          # mask the prompt

            self.items.append((f_ids, labels))

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


def collate(batch, pad_id):
    n = max(len(x[0]) for x in batch)
    ids, labels, mask = [], [], []
    for f, l in batch:
        pad = n - len(f)
        ids.append(f + [pad_id] * pad)
        labels.append(l + [-100] * pad)
        mask.append([1] * len(f) + [0] * pad)
    return (
        torch.tensor(ids),
        torch.tensor(labels),
        torch.tensor(mask),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="unsloth/Qwen3-1.7B")
    ap.add_argument("--data", default="train.jsonl")
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--r", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--seq", type=int, default=1024)
    ap.add_argument("--bs", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    args = ap.parse_args()

    model, tok = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.seq,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.r,
        lora_alpha=args.r,
        lora_dropout=0,
        bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    rows = [json.loads(l) for l in open(args.data)]
    ds = LogDataset(rows, tok, args.seq)
    print(f"loaded {len(ds)} examples")

    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    dl = DataLoader(
        ds, batch_size=args.bs, shuffle=True,
        collate_fn=lambda b: collate(b, pad_id),
    )

    # show one example exactly as the model sees it
    ids, labels, _ = next(iter(dl))
    kept = [i for i, l in zip(ids[0].tolist(), labels[0].tolist()) if l != -100]
    print("--- loss is computed on ---")
    print(tok.decode(kept))
    print("---------------------------")

    steps = math.ceil(len(dl) * args.epochs / args.accum)
    opt = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.lr, weight_decay=0.01,
    )
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=args.lr, total_steps=steps, pct_start=0.03,
    )

    model.train()
    step, done, running = 0, 0, []
    total_batches = int(len(dl) * args.epochs)

    for epoch in range(math.ceil(args.epochs)):
        for batch in dl:
            ids, labels, mask = [t.cuda() for t in batch]
            out = model(input_ids=ids, attention_mask=mask, labels=labels)
            (out.loss / args.accum).backward()
            running.append(out.loss.item())
            done += 1

            if done % args.accum == 0:
                torch.nn.utils.clip_grad_norm_(
                    [p for p in model.parameters() if p.requires_grad], 1.0)
                opt.step()
                if step < steps - 1:
                    sched.step()
                opt.zero_grad()
                step += 1
                if step % 10 == 0:
                    print(f"step {step}/{steps}  loss {sum(running)/len(running):.4f}")
                    running = []

            if done >= total_batches:
                break
        if done >= total_batches:
            break

    print(f"\nfinal loss: {sum(running)/len(running):.4f}" if running else "\ndone")

    model.save_pretrained("./lora_adapter")
    tok.save_pretrained("./lora_adapter")
    model.save_pretrained_merged("./merged", tok, save_method="merged_16bit")
    print("saved ./lora_adapter and ./merged")


if __name__ == "__main__":
    main()
