"""
Demo: normalize log lines with the fine-tuned model + epoch pre-pass.

    python demo.py                  # bundled examples
    python demo.py mylogs.txt       # your own file
    python demo.py mylogs.txt --baseline   # also run Gemini (needs OPENROUTER_API_KEY)
"""
import sys, os, json, time, argparse, torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
from eval import build_prompt, parse, FIELDS
from score_hybrid import epoch_override

BASE, ADAPTER = "unsloth/qwen3-4b-unsloth-bnb-4bit", "arshirazi/tiny-log-parser"

EXAMPLES = [
    '<131>Mar  5 02:10:12 web-07 payments[4471]: TLS handshake aborted by peer [tid=8f2c91aa04bd77e35c1d6b0392ef4a18] took=4.775s',
    '10.14.2.9 - - [22/Jul/2026:09:15:44 +0500] "GET /api/v2/orders HTTP/1.1" 503 812 "-" "curl/8.4.0" rt=7.881',
    'ts=1780543196 level=warn service=inventory msg="stock below threshold" trace=7f3b1c2d4e5a6b8c9d0e1f2a3b4c5d6e latency=340ms',
    '2026-06-18 14:22:09,331 ERROR [payment-worker-3] c.a.p.RefundService - refund gateway timeout traceId=b2e4f6a8c0d2e4f6a8b0c2d4e6f8a0b2 elapsed=2140ms',
    '{"time":1783402811,"severity":"CRITICAL","container":"billing","message":"ledger write failed","duration_us":9120000}',
    '[2026-07-15T03:44:12+05:00] [FATAL] [search-indexer] shard replication halted (tid=e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4) 15.2s',
]

def load():
    tok = AutoTokenizer.from_pretrained(BASE, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(BASE, device_map="auto")
    return tok, PeftModel.from_pretrained(m, ADAPTER).eval()

def run(tok, m, lines, batch=8):
    out = []
    for i in range(0, len(lines), batch):
        chunk = lines[i:i + batch]
        enc = tok([build_prompt(l, []) for l in chunk],
                  return_tensors="pt", padding=True).to(m.device)
        gen = m.generate(**enc, max_new_tokens=120, do_sample=False,
                         pad_token_id=tok.pad_token_id)
        for o in gen:
            out.append(parse(tok.decode(o[enc.input_ids.shape[-1]:],
                                        skip_special_tokens=True)))
    return out

def gemini(lines):
    from openai import OpenAI
    shots = ([json.loads(l) for l in open("train.jsonl")][:3]
             if os.path.exists("train.jsonl") else [])
    c = OpenAI(base_url="https://openrouter.ai/api/v1",
               api_key=os.environ["OPENROUTER_API_KEY"])
    res = []
    for l in lines:
        r = c.chat.completions.create(
            model="google/gemini-3.1-pro-preview", temperature=0, max_tokens=8000,
            messages=[{"role": "user", "content": build_prompt(l, shots)}])
        res.append(parse(r.choices[0].message.content))
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logfile", nargs="?")
    ap.add_argument("--baseline", action="store_true")
    a = ap.parse_args()

    lines = ([l.strip() for l in open(a.logfile) if l.strip()]
             if a.logfile else EXAMPLES)

    if not torch.cuda.is_available():
        sys.exit("Needs a CUDA GPU (4-bit weights). Use the Colab notebook, "
                 "or `python score_hybrid.py` to re-score the saved outputs.")

    tok, m = load()
    t0 = time.time()
    preds = run(tok, m, lines)
    dt = time.time() - t0

    fired = 0
    for i, (l, p) in enumerate(zip(lines, preds)):
        iso = epoch_override(l)
        if p and iso:
            fired += 1
            p = {**p, "timestamp": iso}
            preds[i] = p

    gem = gemini(lines) if a.baseline else [None] * len(lines)

    for l, p, g in zip(lines, preds, gem):
        print("\n" + "=" * 92)
        print("IN  ", l[:88] + ("  [pre-pass]" if epoch_override(l) else ""))
        if not a.baseline:
            print("OUT ", json.dumps(p, indent=6) if p else "[unparseable]")
            continue
        for f in FIELDS:
            x, y = (p or {}).get(f), (g or {}).get(f)
            print(f"  {'  ' if x == y else '<>'} {f:<12} ours={str(x):<36} gemini={y}")

    print(f"\n{'=' * 92}\n{len(lines)} lines in {dt:.1f}s "
          f"({dt / len(lines) * 1000:.0f} ms/line) | pre-pass fired on {fired}")

if __name__ == "__main__":
    main()