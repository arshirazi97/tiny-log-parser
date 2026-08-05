"""
Eval harness: your fine-tune vs. the frontier baseline, same test set,
same prompt spec, same scoring.

Usage:
    python eval.py --runner baseline --n 200
    python eval.py --runner local --model ./outputs/merged --n 200
"""

import argparse
import json
import random
import re
import statistics
import time

FIELDS = ["timestamp", "level", "service", "trace_id", "status_code", "latency_ms", "message"]

# ---------------------------------------------------------------------------
# THE SPEC -- given verbatim to BOTH models. This is what makes the
# comparison fair. Quote it in your writeup.
# ---------------------------------------------------------------------------
SPEC = """Normalize the log line into JSON with exactly these keys:

  timestamp   ISO8601 UTC, second precision, "Z" suffix. Convert from any
              offset. Epoch seconds/millis allowed as input. If the format
              omits the year, assume 2026.
  level       One of: CRITICAL ERROR WARNING INFO DEBUG.
              Map aliases: FATAL/CRIT->CRITICAL, ERR/E->ERROR,
              WARN/W->WARNING, NOTICE/I->INFO, DBG/D->DEBUG.
              Syslog numeric severities: 2->CRITICAL, 3->ERROR, 4->WARNING,
              5/6->INFO, 7->DEBUG.
              If the line has no level field but has an HTTP status code:
              5xx->ERROR, 4xx->WARNING, otherwise INFO.
  service     Lowercase service name.
  trace_id    32-char lowercase hex, or null if absent. Never invent one.
  status_code Integer, or null if not an HTTP event.
  latency_ms  Integer MILLISECONDS. Convert units: "0.234s"->234,
              "234000us"->234, "rt=1.500"->1500. null if absent.
  message     The human-readable message only. For access logs use
              "METHOD /path". Collapse whitespace. No trailing metadata.

Output only the JSON object. No markdown fences, no commentary."""


def build_prompt(raw, shots):
    ex = "\n\n".join(
        f"Log:\n{s['input']}\nJSON:\n{json.dumps(s['output'])}" for s in shots
    )
    return f"{SPEC}\n\n{ex}\n\nLog:\n{raw}\nJSON:"


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

def parse(text):
    """Extract a JSON object from model output. Tolerant of fences."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, c in enumerate(text[start:], start):
        depth += (c == "{") - (c == "}")
        if depth == 0:
            try:
                return json.loads(text[start:i + 1])
            except json.JSONDecodeError:
                return None
    return None


def score(pred, gold):
    """Returns (exact_match, valid_json, {field: bool})."""
    if pred is None or not isinstance(pred, dict):
        return False, False, {f: False for f in FIELDS}
    per = {}
    for f in FIELDS:
        p, g = pred.get(f, "__missing__"), gold[f]
        # accept int-as-string for numeric fields
        if isinstance(g, int) and isinstance(p, str) and p.lstrip("-").isdigit():
            p = int(p)
        per[f] = (p == g)
    return all(per.values()), True, per


def bootstrap_ci(hits, n_boot=2000):
    means = []
    for _ in range(n_boot):
        s = [random.choice(hits) for _ in hits]
        means.append(sum(s) / len(s))
    means.sort()
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]


# ---------------------------------------------------------------------------
# Runners -- swap in whichever baseline you're comparing against
# ---------------------------------------------------------------------------

def runner_baseline(prompts):
    import os
    from openai import OpenAI
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )
    out = []
    for i, p in enumerate(prompts):
        r = client.chat.completions.create(
            model="google/gemini-3.1-pro-preview",
            temperature=0,
            max_tokens=2000,
            messages=[{"role": "user", "content": p}],
        )
        out.append(r.choices[0].message.content)
        if i % 20 == 0:
            print(f"  {i}/{len(prompts)}")
    return out


def runner_local(prompts, model_path):
    """Your fine-tune, via vLLM for throughput."""
    from vllm import LLM, SamplingParams
    llm = LLM(model=model_path, max_model_len=2048)
    sp = SamplingParams(temperature=0, max_tokens=400)
    return [o.outputs[0].text for o in llm.generate(prompts, sp)]


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", choices=["baseline", "local"], required=True)
    ap.add_argument("--model", default=None)
    ap.add_argument("--test", default="test.jsonl")
    ap.add_argument("--train", default="train.jsonl", help="source of few-shot examples")
    ap.add_argument("--shots", type=int, default=3)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    random.seed(0)
    test = [json.loads(l) for l in open(args.test)][: args.n]
    shots = [json.loads(l) for l in open(args.train)][: args.shots]

    # The baseline gets few-shot examples. The fine-tune does not need them
    # (it saw 5k during training) -- give it the bare spec, which is also
    # how it would run in production.
    use_shots = shots if args.runner == "baseline" else []
    prompts = [build_prompt(r["input"], use_shots) for r in test]

    t0 = time.time()
    if args.runner == "baseline":
        raw_outs = runner_baseline(prompts)
    else:
        raw_outs = runner_local(prompts, args.model)
    elapsed = time.time() - t0

    hits, valid, per_field = [], [], {f: [] for f in FIELDS}
    misses = []
    for row, raw in zip(test, raw_outs):
        pred = parse(raw)
        ok, is_valid, per = score(pred, row["output"])
        hits.append(int(ok))
        valid.append(int(is_valid))
        for f in FIELDS:
            per_field[f].append(int(per[f]))
        if not ok:
            misses.append({"input": row["input"], "gold": row["output"], "pred": pred})

    acc = sum(hits) / len(hits)
    lo, hi = bootstrap_ci(hits)

    print(f"\n{'='*58}")
    print(f"runner            {args.runner}  ({args.model or 'api'})")
    print(f"n                 {len(hits)}")
    print(f"exact match       {acc:.1%}   [95% CI {lo:.1%} - {hi:.1%}]")
    print(f"valid JSON        {sum(valid)/len(valid):.1%}")
    print(f"latency / item    {elapsed/len(hits)*1000:.0f} ms")
    print(f"{'-'*58}")
    print("per-field accuracy")
    for f in FIELDS:
        v = sum(per_field[f]) / len(per_field[f])
        bar = "#" * int(v * 30)
        print(f"  {f:<12} {v:6.1%}  {bar}")
    print(f"{'='*58}\n")

    if args.out:
        json.dump(
            {"accuracy": acc, "ci": [lo, hi],
             "per_field": {f: sum(v)/len(v) for f, v in per_field.items()},
             "misses": misses[:40]},
            open(args.out, "w"), indent=2,
        )
        print(f"wrote {args.out}  ({len(misses)} misses, first 40 saved)")


if __name__ == "__main__":
    main()
