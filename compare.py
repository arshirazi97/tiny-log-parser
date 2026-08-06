
import os, sys, json, time, torch

from openai import OpenAI

from eval import build_prompt, parse, FIELDS

from transformers import AutoTokenizer, AutoModelForCausalLM

from peft import PeftModel

lines = [l.strip() for l in open(sys.argv[1] if len(sys.argv)>1 else "messy.log") if l.strip()]

# ---- your model (batched) ----

BASE = "unsloth/qwen3-4b-unsloth-bnb-4bit"

tok = AutoTokenizer.from_pretrained(BASE, padding_side="left")

if tok.pad_token is None: tok.pad_token = tok.eos_token

m = AutoModelForCausalLM.from_pretrained(BASE, device_map="auto")

m = PeftModel.from_pretrained(m, "arshirazi/tiny-log-parser").eval()

t0 = time.time()

enc = tok([build_prompt(l, []) for l in lines], return_tensors="pt", padding=True).to(m.device)

out = m.generate(**enc, max_new_tokens=120, do_sample=False, pad_token_id=tok.pad_token_id)

mine = [parse(tok.decode(o[enc.input_ids.shape[-1]:], skip_special_tokens=True)) for o in out]

mine_t = time.time() - t0

# ---- gemini ----

shots = [json.loads(l) for l in open("train.jsonl")][:3] if os.path.exists("train.jsonl") else []

c = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

gem, t0 = [], time.time()

for i, l in enumerate(lines):

    r = c.chat.completions.create(model="google/gemini-3.1-pro-preview", temperature=0,

        max_tokens=8000, messages=[{"role":"user","content":build_prompt(l, shots)}])

    gem.append(parse(r.choices[0].message.content))

    print(f"  gemini {i+1}/{len(lines)}", end="\r")

gem_t = time.time() - t0

# ---- side by side ----

for l, a, b in zip(lines, mine, gem):

    print("\n" + "="*100)

    print("IN  ", l[:96])

    if a is None or b is None:

        print("  mine:  ", a); print("  gemini:", b); continue

    for f in FIELDS:

        x, y = a.get(f), b.get(f)

        mark = "  " if x == y else "<>"

        print(f"  {mark} {f:<12} mine={str(x):<38} gemini={y}")

d = sum(1 for a,b in zip(mine,gem) if a!=b)

print(f"\n{'='*100}\n{len(lines)} lines | disagree on {d} | "

      f"mine {mine_t:.0f}s total, gemini {gem_t:.0f}s total")

