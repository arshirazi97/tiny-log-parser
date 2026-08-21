#!/usr/bin/env python3
"""Run one arm over a corpus and write {id, pred} for score_arms.py.

    python real-eval/predict.py --arm rules  --corpus real-eval/corpus_dev.jsonl
    python real-eval/predict.py --arm model  --adapter arshirazi/tiny-log-parser-v2
    python real-eval/predict.py --arm gemini --shots 3

Both LLM arms receive schema_v2.SPEC_EVAL -- the frozen training spec plus the
three clarifications labelling forced (ADJUDICATION S1b, F5, M1b). Identical
text to each, so neither is scored against rules it was never given.

The test corpus requires --allow-test. Run it ONCE, at the end, after the dev
numbers have settled. Every accidental peek costs you the sealed test set.
"""
import argparse, json, os, sys, time

sys.path.insert(0, ".")
from eval import parse
from schema_v2 import SPEC_EVAL, FIELDS


def load_corpus(path, allow_test):
    if "test" in os.path.basename(path) and not allow_test:
        sys.exit("Refusing to touch the test corpus without --allow-test.\n"
                 "Settle the dev numbers first; the test set is scored once.")
    return [json.loads(l) for l in open(path) if l.strip()]


# --------------------------------------------------------------------------

def arm_rules(rows, args):
    import importlib.util
    s = importlib.util.spec_from_file_location("rp", "real-eval/rule_parser.py")
    rp = importlib.util.module_from_spec(s)
    s.loader.exec_module(rp)
    return [rp.parse_line(r["raw"])[0] for r in rows]


def arm_model(rows, args):
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    if not torch.cuda.is_available():
        sys.exit("Needs a CUDA GPU (4-bit base weights). Use Colab.")

    tok = AutoTokenizer.from_pretrained(args.base, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = PeftModel.from_pretrained(
        AutoModelForCausalLM.from_pretrained(args.base, device_map="auto"),
        args.adapter).eval()

    prompts = [tok.apply_chat_template(
        [{"role": "system", "content": SPEC_EVAL}, {"role": "user", "content": r["raw"]}],
        tokenize=False, add_generation_prompt=True, enable_thinking=False) for r in rows]

    out = []
    for i in range(0, len(prompts), args.batch):
        enc = tok(prompts[i:i + args.batch], return_tensors="pt",
                  padding=True).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=args.max_new,
                                 do_sample=False, pad_token_id=tok.pad_token_id)
        for o in gen:
            out.append(parse(tok.decode(o[enc.input_ids.shape[-1]:],
                                        skip_special_tokens=True)))
        print(f"  {min(i + args.batch, len(prompts))}/{len(prompts)}", flush=True)
    return out


def arm_gemini(rows, args):
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=os.environ["OPENROUTER_API_KEY"])

    # The baseline gets few-shot examples; the fine-tune gets none. Same
    # deliberate handicap as the v1 comparison. --shots 0 removes it.
    shots = ""
    if args.shots:
        src = [json.loads(l) for l in open(args.shots_file)][: args.shots]
        shots = "\n\n" + "\n\n".join(
            f"Log:\n{s['input']}\nJSON:\n{json.dumps(s['output'])}" for s in src)

    out = []
    for i, r in enumerate(rows):
        for attempt in range(4):
            try:
                resp = client.chat.completions.create(
                    model=args.gemini_model, temperature=0, max_tokens=8000,
                    messages=[{"role": "user",
                               "content": f"{SPEC_EVAL}{shots}\n\nLog:\n{r['raw']}\nJSON:"}])
                out.append(parse(resp.choices[0].message.content))
                break
            except Exception as e:                     # rate limit / transient
                if attempt == 3:
                    print(f"  giving up on {r['id']}: {e}", file=sys.stderr)
                    out.append(None)
                else:
                    time.sleep(2 ** attempt)
        if i % 20 == 0:
            print(f"  {i}/{len(rows)}", flush=True)
    return out


ARMS = {"rules": arm_rules, "model": arm_model, "gemini": arm_gemini}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=list(ARMS), required=True)
    ap.add_argument("--corpus", default="real-eval/corpus_dev.jsonl")
    ap.add_argument("--out", default=None)
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--base", default="unsloth/qwen3-4b-unsloth-bnb-4bit")
    ap.add_argument("--adapter", default="arshirazi/tiny-log-parser-v2")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--max-new", type=int, default=200)
    ap.add_argument("--gemini-model", default="google/gemini-3.1-pro-preview")
    ap.add_argument("--shots", type=int, default=3)
    ap.add_argument("--shots-file", default="train_v2.jsonl")
    args = ap.parse_args()

    rows = load_corpus(args.corpus, args.allow_test)
    split = "test" if "test" in os.path.basename(args.corpus) else "dev"
    out_path = args.out or f"real-eval/preds_{split}_{args.arm}.jsonl"

    print(f"{len(rows)} lines | arm={args.arm} | spec=SPEC_EVAL "
          f"({len(SPEC_EVAL)} chars)")
    if args.arm == "model":
        print(f"adapter {args.adapter}")
    if args.arm == "gemini":
        print(f"{args.gemini_model} | shots={args.shots}")

    t0 = time.time()
    preds = ARMS[args.arm](rows, args)
    elapsed = time.time() - t0

    n_bad = sum(1 for p in preds if not isinstance(p, dict))
    with open(out_path, "w") as f:
        for r, p in zip(rows, preds):
            f.write(json.dumps({"id": r["id"], "source": r["source"],
                                "stratum": r["stratum"], "raw": r["raw"],
                                "pred": p}) + "\n")
    print(f"\nwrote {out_path}  ({len(preds)} rows, {n_bad} unparseable)")
    print(f"{elapsed:.0f}s total, {elapsed / len(rows) * 1000:.0f} ms/line")


if __name__ == "__main__":
    main()
