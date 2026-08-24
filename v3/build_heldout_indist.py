#!/usr/bin/env python3
"""Sample held-out IN-DISTRIBUTION lines: same ten systems v3 trained on,
lines it has never seen.

This answers a narrower question than P1 did. P1 asked whether v3 survives
unseen *templates*; this asks the prior question -- how good is v3 on exactly
the formats it was trained for, when the specific lines are new.

The pool is Loghub-1.0's `<System>_2k.log` (real-eval/.cache, via
v3/fetch_loghub1.py). v3 trained on Loghub-2.0, so the two do not intersect:
the builder verifies that rather than assuming it, and also excludes anything
already in corpus_p1.jsonl so this does not re-score P1 lines.

    python3 v3/fetch_loghub1.py                     # if .cache is empty
    python3 v3/build_heldout_indist.py --n 50 --out real-eval/corpus_heldout.jsonl

There are no gold labels here and none are invented. Scoring is by adjudicated
disagreement: run rules and v3, diff them, hand-check only the lines where they
differ. `rule_parser.py` scored 100.0% (96/96) on the P1 in-distribution slice,
so it is a serviceable reference on THIS distribution -- and nowhere else.
"""
import argparse, hashlib, json, random, sys
from pathlib import Path

# the ten systems in train_v3.jsonl. BGL/Thunderbird/Mac/HPC are the
# out-of-distribution four and are deliberately not sampled here.
SYSTEMS = ["Spark", "Linux", "Hadoop", "HDFS", "Apache", "Zookeeper",
           "HealthApp", "OpenSSH", "OpenStack", "Proxifier"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="lines per system")
    ap.add_argument("--cache", default="real-eval/.cache")
    ap.add_argument("--train", default="v3/train_v3.jsonl")
    ap.add_argument("--exclude", default="real-eval/corpus_p1.jsonl")
    ap.add_argument("--seed", type=int, default=20260824)
    ap.add_argument("--out", default="real-eval/corpus_heldout.jsonl")
    a = ap.parse_args()

    train = {json.loads(l)["input"] for l in open(a.train) if l.strip()}
    seen = set(train)
    if Path(a.exclude).exists():
        seen |= {json.loads(l)["raw"] for l in open(a.exclude) if l.strip()}

    rng = random.Random(a.seed)
    rows, leaked = [], 0
    for s in SYSTEMS:
        f = Path(a.cache) / f"{s}_2k.log"
        if not f.exists():
            sys.exit(f"missing {f} -- run: python3 v3/fetch_loghub1.py")
        lines = [l.strip() for l in f.read_text(errors="replace").splitlines()
                 if l.strip()]
        pool = [l for l in lines if l not in seen]
        leaked += len(lines) - len(pool)
        if len(pool) < a.n:
            print(f"  {s}: only {len(pool)} held-out lines, taking all")
        for raw in rng.sample(pool, min(a.n, len(pool))):
            rows.append({"id": hashlib.sha1(raw.encode()).hexdigest()[:12],
                         "raw": raw, "source": s, "stratum": "in-dist-heldout"})

    rng.shuffle(rows)
    with open(a.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    print(f"\nwrote {a.out}: {len(rows)} lines from {len(SYSTEMS)} systems")
    print(f"excluded as already-seen: {leaked} "
          f"({'clean -- 1.0 and 2.0 do not overlap' if not leaked else 'CHECK THIS'})")
    from collections import Counter
    for s, n in Counter(r["source"] for r in rows).most_common():
        print(f"  {s:<12}{n:>5}")


if __name__ == "__main__":
    main()
