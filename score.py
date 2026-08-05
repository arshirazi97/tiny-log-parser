"""Score local_raw.json against test.jsonl using eval.py's verifier."""
import json, random
from eval import parse, score, bootstrap_ci, FIELDS

raw = json.load(open("local_raw.json"))
outs = raw["outputs"]
rows = [json.loads(l) for l in open("test.jsonl")][:len(outs)]

random.seed(0)
hits, valid, per = [], [], {f: [] for f in FIELDS}
misses = []
for row, txt in zip(rows, outs):
    pred = parse(txt)
    ok, is_valid, fields = score(pred, row["output"])
    hits.append(int(ok)); valid.append(int(is_valid))
    for f in FIELDS: per[f].append(int(fields[f]))
    if not ok:
        misses.append({"input": row["input"], "gold": row["output"], "pred": pred})

acc = sum(hits)/len(hits)
lo, hi = bootstrap_ci(hits)
ms = raw["elapsed"]/len(outs)*1000

print(f"\n{'='*58}")
print(f"runner            local  (./merged)")
print(f"n                 {len(hits)}")
print(f"exact match       {acc:.1%}   [95% CI {lo:.1%} - {hi:.1%}]")
print(f"valid JSON        {sum(valid)/len(valid):.1%}")
print(f"latency / item    {ms:.0f} ms")
print(f"{'-'*58}")
print("per-field accuracy")
for f in FIELDS:
    v = sum(per[f])/len(per[f])
    print(f"  {f:<12} {v:6.1%}  {'#'*int(v*30)}")
print(f"{'='*58}\n")

json.dump({"accuracy": acc, "ci": [lo, hi], "latency_ms": ms,
           "per_field": {f: sum(v)/len(v) for f, v in per.items()},
           "misses": misses[:40]}, open("mine.json","w"), indent=2)
print(f"wrote mine.json  ({len(misses)} misses)")
