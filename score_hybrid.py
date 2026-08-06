"""
Hybrid system: deterministic epoch conversion + the fine-tuned model.

Bare epoch integers are detected with a regex and converted with
datetime.utcfromtimestamp -- exact, instant, no model involved. Everything
else is left to the model. Scored on the same 200-example test set.

    python score_hybrid.py
"""

import json
import random
import re
from datetime import datetime, timezone

from eval import parse, score, bootstrap_ci, FIELDS

# 10-digit integers in the plausible epoch range, standing alone
EPOCH = re.compile(r'(?<![\d.])(1[6-9]\d{8}|1[6-9]\d{11})(?![\d.])')


def epoch_override(raw_input):
    """If the log line carries a bare epoch, return the exact ISO timestamp."""
    m = EPOCH.search(raw_input)
    if not m:
        return None
    n = int(m.group(1))
    if n > 10**11:
        n //= 1000
    dt = datetime.fromtimestamp(n, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    raw = json.load(open("local_raw.json"))
    outs = raw["outputs"]
    rows = [json.loads(l) for l in open("test.jsonl")][:len(outs)]

    random.seed(0)
    results = {}

    for mode in ("model only", "model + epoch pre-pass"):
        hits, valid, per = [], [], {f: [] for f in FIELDS}
        misses, applied = [], 0

        for row, txt in zip(rows, outs):
            pred = parse(txt)
            if mode.endswith("pre-pass") and isinstance(pred, dict):
                iso = epoch_override(row["input"])
                if iso:
                    pred = dict(pred)
                    pred["timestamp"] = iso
                    applied += 1

            ok, is_valid, fields = score(pred, row["output"])
            hits.append(int(ok))
            valid.append(int(is_valid))
            for f in FIELDS:
                per[f].append(int(fields[f]))
            if not ok:
                misses.append({"input": row["input"],
                               "gold": row["output"], "pred": pred})

        acc = sum(hits) / len(hits)
        lo, hi = bootstrap_ci(hits)
        results[mode] = {
            "accuracy": acc, "ci": [lo, hi],
            "per_field": {f: sum(v) / len(v) for f, v in per.items()},
            "n_misses": len(misses), "misses": misses[:40],
            "epoch_overrides": applied,
        }

        print(f"\n{'='*58}")
        print(f"{mode}")
        print(f"exact match       {acc:.1%}   [95% CI {lo:.1%} - {hi:.1%}]")
        if applied:
            print(f"epoch overrides   {applied}/{len(rows)} inputs")
        print(f"{'-'*58}")
        for f in FIELDS:
            v = sum(per[f]) / len(per[f])
            print(f"  {f:<12} {v:6.1%}  {'#'*int(v*30)}")
        print(f"{'='*58}")

    # what still fails after the pre-pass
    rest = results["model + epoch pre-pass"]["misses"]
    print(f"\nremaining misses: {results['model + epoch pre-pass']['n_misses']}")
    for m in rest[:8]:
        bad = [f for f in FIELDS if m["gold"][f] != (m["pred"] or {}).get(f)]
        print(f"\n  fields wrong: {bad}")
        print(f"  in   {m['input'][:90]}")
        for f in bad:
            print(f"  {f:<12} gold={m['gold'][f]!r}  pred={(m['pred'] or {}).get(f)!r}")

    json.dump(results, open("hybrid.json", "w"), indent=2)
    print("\nwrote hybrid.json")


if __name__ == "__main__":
    main()
