import sys, re, time, torch
from datetime import datetime, timezone
from eval import build_prompt, parse
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

EPOCH = re.compile(r'(?:^|[\s=:"])(\d{10}|\d{13})(?:[\s,"}]|$)')

def prepass(line):
    m = EPOCH.search(line)
    if not m: return None
    v = int(m.group(1))
    if len(m.group(1)) == 13: v //= 1000
    return datetime.fromtimestamp(v, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

lines = [l.strip() for l in open(sys.argv[1] if len(sys.argv)>1 else "messy.log") if l.strip()]

BASE = "unsloth/qwen3-4b-unsloth-bnb-4bit"
tok = AutoTokenizer.from_pretrained(BASE, padding_side="left")
if tok.pad_token is None: tok.pad_token = tok.eos_token
m = AutoModelForCausalLM.from_pretrained(BASE, device_map="auto")
m = PeftModel.from_pretrained(m, "arshirazi/tiny-log-parser").eval()

t0 = time.time()
enc = tok([build_prompt(l, []) for l in lines], return_tensors="pt", padding=True).to(m.device)
out = m.generate(**enc, max_new_tokens=120, do_sample=False, pad_token_id=tok.pad_token_id)
raw = [parse(tok.decode(o[enc.input_ids.shape[-1]:], skip_special_tokens=True)) for o in out]
el = time.time() - t0

fired = corrected = 0
for l, r in zip(lines, raw):
    ts = prepass(l)
    print("\n" + "="*96)
    print("IN  ", l[:92])
    if r is None:
        print("  [unparseable]"); continue
    if ts:
        fired += 1
        before = r.get("timestamp")
        if before != ts:
            corrected += 1
            print(f"  PRE-PASS  model said {before}  ->  {ts}")
        else:
            print(f"  PRE-PASS  model already correct ({ts})")
        r = {**r, "timestamp": ts}
    print("  ", r)

print(f"\n{'='*96}\n{len(lines)} lines in {el:.0f}s  |  pre-pass fired on {fired}, corrected {corrected}")
