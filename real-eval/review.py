#!/usr/bin/env python3
"""Review proposed labels efficiently: sample, inspect, approve.

Labels were generated per source, so errors are systematic -- checking one line
per source catches a whole family. This shows a stratified sample rather than
all 127.

    python real-eval/review.py                      # 1 per source + all flagged
    python real-eval/review.py --per-source 3       # wider sample
    python real-eval/review.py --source Linux       # one family in full
    python real-eval/review.py --field level        # just one field, all rows
    python real-eval/review.py --approve            # stamp _review: human-approved
"""
import argparse, json, random
from collections import defaultdict

FIELDS = ["timestamp", "level", "service", "trace_id",
          "status_code", "latency_ms", "message"]


def show(r):
    print("=" * 100)
    fl = f"   FLAGS: {', '.join(r['_flags'])}" if r.get("_flags") else ""
    print(f"{r['source']}  ({r['stratum']}){fl}")
    print(f"  {r['raw']}")
    print("  " + "-" * 96)
    for f in FIELDS:
        v = r["label"][f]
        mark = "  " if v is not None else "->"   # highlight abstentions
        print(f"  {mark} {f:<12} {v!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="real-eval/labels_test.jsonl")
    ap.add_argument("--per-source", type=int, default=1)
    ap.add_argument("--source", default=None)
    ap.add_argument("--field", default=None)
    ap.add_argument("--flagged-only", action="store_true")
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.labels) if l.strip()]

    if args.approve:
        for r in rows:
            r["_review"] = "human-approved"
        with open(args.labels, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"stamped {len(rows)} rows _review: human-approved")
        return

    if args.field:
        print(f"{args.field} across all {len(rows)} rows, grouped by value:\n")
        by = defaultdict(list)
        for r in rows:
            by[repr(r["label"][args.field])].append(r["source"])
        for v, srcs in sorted(by.items(), key=lambda kv: -len(kv[1])):
            c = defaultdict(int)
            for s in srcs:
                c[s] += 1
            print(f"  {v:<50} {len(srcs):>3}  {dict(c)}")
        return

    if args.source:
        sel = [r for r in rows if r["source"] == args.source]
    elif args.flagged_only:
        sel = [r for r in rows if r.get("_flags")]
    else:
        random.seed(args.seed)
        by = defaultdict(list)
        for r in rows:
            by[r["source"]].append(r)
        sel = [r for s in sorted(by) for r in random.sample(
            by[s], min(args.per_source, len(by[s])))]
        sel += [r for r in rows if r.get("_flags") and r not in sel]

    for r in sel:
        show(r)
    print("=" * 100)
    print(f"\nshown {len(sel)} of {len(rows)}   "
          f"({sum(1 for r in rows if r.get('_flags'))} flagged in total)")
    print("Disagree with one? Edit labels_test.jsonl directly, or tell me the id.")
    print("Happy with all of it? python real-eval/review.py --approve\n")


if __name__ == "__main__":
    main()
