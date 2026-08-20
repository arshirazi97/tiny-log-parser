#!/usr/bin/env python3
"""Does the existing fine-tune abstain? Label-free probe on the dev corpus.

The model was trained on 20,000 examples in which `level` and `service` were
never null -- so it may be structurally unable to emit null. That would make it
fail the sparse stratum by construction, not by generalization failure.

This measures that WITHOUT needing hand labels: if the model emits a non-null
level on every line, including lines that carry no level token at all, it
cannot abstain. Run this before deciding whether to retrain.

    python real-eval/probe_abstention.py --corpus real-eval/corpus_dev.jsonl

Needs a CUDA GPU (4-bit base weights). Colab T4 is enough.
Touch the dev corpus only. The test corpus stays sealed.
"""
import argparse, json, re, sys
from collections import Counter, defaultdict

sys.path.insert(0, ".")
from eval import SPEC, parse, FIELDS

BASE = "unsloth/qwen3-4b-unsloth-bnb-4bit"
ADAPTER = "arshirazi/tiny-log-parser"      # v1; override with --adapter

# --------------------------------------------------------------------------
# Conservative presence detectors.
#
# These deliberately OVER-report presence, so the hallucination rates they
# produce are understated. A conclusion that survives an understated estimate
# is safe; one that needs an inflated estimate is not.
# --------------------------------------------------------------------------

LEVEL_TOKENS = r"TRACE|DEBUG|DBG|INFO|NOTICE|WARN|WARNING|ERROR|ERR|FATAL|CRIT|CRITICAL"
HAS_LEVEL = re.compile(rf"\b(?:{LEVEL_TOKENS})\b", re.I)
HAS_TRACE = re.compile(r"\b[0-9a-f]{32}\b|req-[0-9a-f]{8}-[0-9a-f-]{27}", re.I)
HAS_STATUS = re.compile(r'HTTP/\d\.\d"?\s+\d{3}\b|\bstatus(?:_code)?\s*[=:]\s*\d{3}\b', re.I)
HAS_LATENCY = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|us|µs|sec|s)\b|\b(?:time|took|elapsed|duration|latency|rt)\s*[=:]", re.I)

DETECTORS = {
    "level": HAS_LEVEL,
    "trace_id": HAS_TRACE,
    "status_code": HAS_STATUS,
    "latency_ms": HAS_LATENCY,
}


def build_chat(tok, raw):
    return tok.apply_chat_template(
        [{"role": "system", "content": SPEC}, {"role": "user", "content": raw}],
        tokenize=False, add_generation_prompt=True, enable_thinking=False,
    )


def build_flat(tok, raw):
    return f"{SPEC}\n\nLog:\n{raw}\nJSON:"


def generate(tok, model, prompts, batch, max_new):
    import torch
    out = []
    for i in range(0, len(prompts), batch):
        chunk = prompts[i:i + batch]
        enc = tok(chunk, return_tensors="pt", padding=True).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=max_new, do_sample=False,
                                 pad_token_id=tok.pad_token_id)
        for o in gen:
            out.append(tok.decode(o[enc.input_ids.shape[-1]:], skip_special_tokens=True))
        print(f"  {min(i + batch, len(prompts))}/{len(prompts)}", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="real-eval/corpus_dev.jsonl")
    ap.add_argument("--prompt", choices=["chat", "flat"], default="chat",
                    help="chat = the format the model was trained and scored with "
                         "(run_local.py); flat = what demo.py and the notebook use")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--max-new", type=int, default=160)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--adapter", default=ADAPTER,
                    help="HF repo or local path of the LoRA adapter to probe")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--out", default="real-eval/probe_dev.json")
    args = ap.parse_args()

    if "test" in args.corpus:
        sys.exit("Refusing to touch the test corpus. Probe on dev only.")

    rows = [json.loads(l) for l in open(args.corpus) if l.strip()][: args.limit]
    print(f"{len(rows)} lines from {args.corpus}\n")

    import torch
    if not torch.cuda.is_available():
        sys.exit("Needs a CUDA GPU (4-bit weights). Run this on Colab.")
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel

    print(f"base    {args.base}\nadapter {args.adapter}\n")
    tok = AutoTokenizer.from_pretrained(args.base, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = PeftModel.from_pretrained(
        AutoModelForCausalLM.from_pretrained(args.base, device_map="auto"),
        args.adapter).eval()

    builder = build_chat if args.prompt == "chat" else build_flat
    raws = generate(tok, model, [builder(tok, r["raw"]) for r in rows],
                    args.batch, args.max_new)
    preds = [parse(t) for t in raws]

    # ---------------- analysis ----------------
    unparseable = sum(1 for p in preds if not isinstance(p, dict))
    null_rate = {f: 0 for f in FIELDS}
    absent = defaultdict(list)      # field -> rows where the line has no such token
    by_source = defaultdict(lambda: {"n": 0, "level_nonnull": 0, "service_nonnull": 0})

    records = []
    for row, txt, pred in zip(rows, raws, preds):
        p = pred if isinstance(pred, dict) else {}
        for f in FIELDS:
            if p.get(f, "__missing__") is None:
                null_rate[f] += 1
        s = by_source[row["source"]]
        s["n"] += 1
        s["level_nonnull"] += int(p.get("level") is not None)
        s["service_nonnull"] += int(p.get("service") is not None)

        for f, rx in DETECTORS.items():
            if not rx.search(row["raw"]):
                absent[f].append((row, p.get(f)))

        records.append({"id": row["id"], "source": row["source"],
                        "stratum": row["stratum"], "raw": row["raw"],
                        "pred": pred, "raw_output": txt.strip()[:400]})

    n = len(rows)
    print(f"\n{'='*72}\nprompt format     {args.prompt}")
    print(f"lines             {n}")
    print(f"unparseable       {unparseable}")
    print(f"{'-'*72}\nmodel null-rate per field  (can it abstain at all?)")
    for f in FIELDS:
        v = null_rate[f] / n
        print(f"  {f:<12} {v:6.1%}  ({null_rate[f]}/{n})  {'#' * int(v * 30)}")

    print(f"{'-'*72}\nhallucination on lines with NO such token present")
    print("(detectors over-report presence, so these are LOWER bounds)")
    summary = {}
    for f in DETECTORS:
        rowsf = absent[f]
        if not rowsf:
            print(f"  {f:<12} n/a  (detector found the token on every line)")
            continue
        bad = [(r, v) for r, v in rowsf if v is not None]
        summary[f] = {"n_absent": len(rowsf), "n_hallucinated": len(bad),
                      "rate": len(bad) / len(rowsf)}
        print(f"  {f:<12} {len(bad)}/{len(rowsf)} = {len(bad)/len(rowsf):6.1%} non-null "
              f"where the line has no {f}")
        for r, v in bad[:3]:
            print(f"      {r['source']:<10} pred={v!r}")
            print(f"      line: {r['raw'][:88]}")

    print(f"{'-'*72}\nper-source: how often the model emits a non-null level / service")
    for src in sorted(by_source):
        s = by_source[src]
        print(f"  {src:<11} n={s['n']:<3}  level {s['level_nonnull']}/{s['n']}"
              f"   service {s['service_nonnull']}/{s['n']}")

    print(f"{'='*72}")
    lvl_null, svc_null = null_rate["level"], null_rate["service"]
    if lvl_null == 0 and svc_null == 0:
        print("VERDICT  The model never emitted null for level or service on any line.")
        print("         It cannot abstain. Retraining with null-bearing examples is")
        print("         required before the real-log eval measures anything.")
    else:
        print(f"VERDICT  The model emitted null for level on {lvl_null}/{n} lines and")
        print(f"         service on {svc_null}/{n}. It has some abstention behaviour --")
        print("         check the per-source table before deciding to retrain.")
    print(f"{'='*72}\n")

    json.dump({"adapter": args.adapter, "prompt": args.prompt, "n": n, "unparseable": unparseable,
               "null_rate": {f: null_rate[f] / n for f in FIELDS},
               "hallucination": summary,
               "by_source": dict(by_source), "records": records},
              open(args.out, "w"), indent=2)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
