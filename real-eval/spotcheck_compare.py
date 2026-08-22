#!/usr/bin/env python3
"""Agreement between the blind spot-check and the gold labels.

    python3 real-eval/spotcheck_compare.py

`labels_p1.jsonl` is model-written (Claude applying ADJUDICATION.md), reviewed
by the author. Review is weak evidence: the reviewer sees the proposed value and
tends to assent. `spotcheck_p1.jsonl` is the author labelling a seeded random
subset from the raw lines alone, with the gold neither loaded nor displayed.

The agreement rate below is the only independent measure of label quality this
corpus admits -- Loghub-2.0 ships no Level or Component column, so
validate_labels_loghub.py cannot run on P1.

Report it with the results, whichever way it falls. A low rate does not
invalidate the gold; it bounds how much weight the gold can carry.
"""
import json, sys
from pathlib import Path

FIELDS = ["timestamp", "level", "service", "trace_id", "status_code", "latency_ms"]


def load(p):
    if not p.exists():
        sys.exit(f"missing {p}")
    return {json.loads(l)["id"]: json.loads(l)
            for l in p.read_text().splitlines() if l.strip()}


def main():
    out = Path("real-eval")
    gold, spot = load(out / "labels_p1.jsonl"), load(out / "spotcheck_p1.jsonl")
    ids = [i for i in spot if i in gold]
    if not ids:
        sys.exit("no overlap between spotcheck_p1.jsonl and labels_p1.jsonl")

    per = {f: 0 for f in FIELDS}
    exact = 0
    diffs = []
    for i in ids:
        g, s = gold[i]["label"], spot[i]["label"]
        ok = True
        for f in FIELDS:
            if str(g.get(f)) == str(s.get(f)):
                per[f] += 1
            else:
                ok = False
                diffs.append((gold[i]["source"], f, g.get(f), s.get(f), gold[i]["raw"]))
        exact += ok

    n = len(ids)
    print(f"blind spot-check: {n} lines\n")
    print(f"  six-field exact agreement   {exact}/{n}  ({exact/n:.1%})\n")
    for f in FIELDS:
        print(f"  {f:12} {per[f]:3}/{n}  ({per[f]/n:5.1%})")
    if diffs:
        print(f"\n{len(diffs)} field disagreement(s):\n")
        for src, f, g, s, raw in diffs:
            print(f"  [{src}] {f}")
            print(f"     gold      {g!r}")
            print(f"     spotcheck {s!r}")
            print(f"     line      {raw[:110]}")
            print()
        print("Each of these is a real question about the rules, not noise.")
        print("Resolve them against ADJUDICATION.md and record the resolution.")
    else:
        print("\nNo disagreements.")


if __name__ == "__main__":
    main()
