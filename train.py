"""
LoRA fine-tune Qwen3-1.7B for log normalization.

    python train.py                      # default: 2 epochs
    python train.py --epochs 3 --r 32    # if underfitting

Outputs:
    ./lora_adapter/    LoRA weights (small, this is what you push to HF)
    ./merged/          full merged model in fp16 (this is what vLLM serves)
"""

import argparse
import json

from datasets import Dataset
from trl import SFTTrainer, SFTConfig
from unsloth import FastLanguageModel
from unsloth.chat_templates import train_on_responses_only

# Must be byte-identical to the SPEC in eval.py, or train/serve skew will
# silently cost you several points of accuracy.
from eval import SPEC


def build_messages(raw, target=None):
    """Single source of truth for prompt format. eval.py imports this too."""
    msgs = [
        {"role": "system", "content": SPEC},
        {"role": "user", "content": raw},
    ]
    if target is not None:
        msgs.append({"role": "assistant", "content": json.dumps(target)})
    return msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="unsloth/Qwen3-1.7B")
    ap.add_argument("--data", default="train.jsonl")
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--r", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--seq", type=int, default=1024)
    args = ap.parse_args()

    model, tokenizer = FastLanguageModel.from_pretrained(
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
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    rows = [json.loads(l) for l in open(args.data)]
    texts = [
        tokenizer.apply_chat_template(
            build_messages(r["input"], r["output"]),
            tokenize=False,
            enable_thinking=False,      # extraction task -- no reasoning trace
        )
        for r in rows
    ]
    ds = Dataset.from_dict({"text": texts})
    print(f"loaded {len(ds)} examples")
    print("--- sample ---\n" + texts[0][:900] + "\n--------------")

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds,
        args=SFTConfig(
            dataset_text_field="text",
            max_seq_length=args.seq,
            per_device_train_batch_size=8,
            gradient_accumulation_steps=2,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            warmup_ratio=0.03,
            lr_scheduler_type="linear",
            optim="adamw_8bit",
            weight_decay=0.01,
            logging_steps=10,
            save_strategy="no",
            seed=42,
            output_dir="./ckpt",
            report_to="none",
        ),
    )

    # Mask the prompt -- compute loss only on the JSON the model must produce.
    # Skipping this wastes capacity learning to regurgitate the spec.
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )

    stats = trainer.train()
    print(f"\ntrain loss: {stats.training_loss:.4f}")

    model.save_pretrained("./lora_adapter")
    tokenizer.save_pretrained("./lora_adapter")
    model.save_pretrained_merged("./merged", tokenizer, save_method="merged_16bit")
    print("saved ./lora_adapter and ./merged")


if __name__ == "__main__":
    main()
