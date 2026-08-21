#!/usr/bin/env python3
"""Score one or more arms against hand labels, and compare them pairwise.

`probe_abstention.py` only measures whether a system abstains. This measures
whether it is RIGHT -- which needs labels, and is the whole reason the corpus
had to be hand-annotated.

Arms:
    rules            the deterministic parser, computed here
    <name>=<path>    a probe JSON, or a JSONL of {"id": ..., "pred": {...}}

    python real-eval/score_arms.py --labels real-eval/labels_dev.jsonl \
        rules v2=real-eval/probe_dev_v2.json

Reported per arm:
  exact        all seven fields
  six-field    excluding message (ADJUDICATION M2 -- message is the most
               judgement-dependent field and should not swamp extraction)
  per-field    accuracy for each field
  halluc.      non-null emitted where the gold is null, the metric that cannot
               be gamed by inverting a generator
  abstain      null emitted where the gold is null

Between arms: McNemar's exact test on six-field match. Paired, which is far
more powerful than comparing two independent confidence intervals at n=127.
"""
import argparse, json, math, random, re, sys
from collections import defaultdict

sys.path.insert(0, ".")
FIELDS = ["timestamp", "level", "service", "trace_id",
          "status_code", "latency_ms", "message"]
SIX = [f for f in FIELDS if f != "message"]


def norm(v):
    """Compare like with like: 340 == 340.0, and collapse message whitespace."""
    if isinstance(v, str):
        return re.sub(r"\s+", " ", v).strip()
    return v


def eq(a, b):
    a, b = norm(a), norm(b)
    if a is None or b is None:
        return a is b or (a is None and b is None)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    # a numeric field the model returned as a string
    if isinstance(a, str) and isinstance(b, (int, float)):
        try:
            return abs(float(a) - float(b)) < 1e-9
        except ValueError:
            return False
    if isinstance(b, str) and isinstance(a, (int, float)):
        return eq(b, a)
    return a == b


def load_preds(spec, corpus_rows):
    """spec is 'rules' or 'name=path'. Returns (name, {id: pred|None})."""
    if spec == "rules":
        from importlib import import_module
        rp = import_module("real-eval.rule_parser") if False else None
        import importlib.util
        s = importlib.util.spec_from_file_location("rp", "real-eval/rule_parser.py")
        rp = importlib.util.module_from_spec(s)
        s.loader.exec_module(rp)
        return "rules", {r["id"]: rp.parse_line(r["raw"])[0] for r in corpus_rows}

    name, path = spec.split("=", 1)
    raw = open(path).read().strip()
    if raw.startswith("{"):                       # probe JSON
        d = json.loads(raw)
        return name, {r["id"]: r["pred"] for r in d["records"]}
    out = {}                                       # JSONL
    for line in raw.splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["id"]] = r.get("pred")
    return name, out


def score(labels, preds):
    res = {"exact": [], "six": [], "field": {f: [] for f in FIELDS},
           "halluc": {f: [0, 0] for f in FIELDS},   # [wrong, opportunities]
           "abstain": {f: [0, 0] for f in FIELDS},
           "unparseable": 0, "misses": []}
    for row in labels:
        gold, p = row["label"], preds.get(row["id"])
        if not isinstance(p, dict):
            res["unparseable"] += 1
            p = {}
        per = {f: eq(p.get(f, "__missing__"), gold[f]) for f in FIELDS}
        res["exact"].append(int(all(per.values())))
        res["six"].append(int(all(per[f] for f in SIX)))
        for f in FIELDS:
            res["field"][f].append(int(per[f]))
            if gold[f] is None:                     # a chance to abstain
                res["halluc"][f][1] += 1
                res["abstain"][f][1] += 1
                if p.get(f) is not None:
                    res["halluc"][f][0] += 1
                else:
                    res["abstain"][f][0] += 1
        if not all(per[f] for f in SIX):
            res["misses"].append({
                "id": row["id"], "source": row["source"], "raw": row["raw"][:100],
                "wrong": {f: {"gold": gold[f], "pred": p.get(f)}
                          for f in SIX if not per[f]}})
    return res


def boot(hits, n=2000):
    if not hits:
        return 0.0, 0.0
    m = sorted(sum(random.choice(hits) for _ in hits) / len(hits) for _ in range(n))
    return m[int(0.025 * n)], m[int(0.975 * n)]


def mcnemar(a, b):
    """Exact two-sided binomial test on discordant pairs."""
    bb = sum(1 for x, y in zip(a, b) if x and not y)
    cc = sum(1 for x, y in zip(a, b) if y and not x)
    n = bb + cc
    if n == 0:
        return bb, cc, 1.0
    k = min(bb, cc)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n * 2
    return bb, cc, min(1.0, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="real-eval/labels_dev.jsonl")
    ap.add_argument("--stratum", choices=["all", "rich", "sparse"], default="all")
    ap.add_argument("--show-misses", type=int, default=0)
    ap.add_argument("arms", nargs="+", help="'rules' or 'name=path'")
    args = ap.parse_args()

    labels = [json.loads(l) for l in open(args.labels) if l.strip()]
    if args.stratum != "all":
        labels = [r for r in labels if r["stratum"] == args.stratum]
    pending = sum(1 for r in labels if r.get("_review") == "pending")

    random.seed(0)
    results = {}
    for spec in args.arms:
        name, preds = load_preds(spec, labels)
        results[name] = score(labels, preds)

    n = len(labels)
    print(f"\n{'=' * 74}")
    print(f"labels {args.labels}   n={n}   stratum={args.stratum}")
    if pending:
        print(f"*** {pending}/{n} labels are _review: pending -- PROVISIONAL ***")
    print(f"{'-' * 74}")
    print(f"{'arm':<10}{'exact':>10}{'six-field':>12}{'95% CI (six)':>22}{'unparseable':>14}")
    for name, r in results.items():
        lo, hi = boot(r["six"])
        print(f"{name:<10}{sum(r['exact'])/n:>9.1%}{sum(r['six'])/n:>12.1%}"
              f"{f'{lo:.1%} - {hi:.1%}':>22}{r['unparseable']:>14}")

    print(f"{'-' * 74}\nper-field accuracy")
    print(f"{'field':<13}" + "".join(f"{k:>12}" for k in results))
    for f in FIELDS:
        print(f"  {f:<11}" + "".join(
            f"{sum(r['field'][f])/n:>12.1%}" for r in results.values()))

    print(f"{'-' * 74}\nhallucination -- non-null emitted where gold is null")
    print(f"{'field':<13}" + "".join(f"{k:>12}" for k in results))
    for f in FIELDS:
        cells = ""
        for r in results.values():
            bad, opp = r["halluc"][f]
            cells += f"{f'{bad}/{opp}':>12}" if opp else f"{'-':>12}"
        print(f"  {f:<11}{cells}")

    if len(results) > 1:
        print(f"{'-' * 74}\nMcNemar on six-field match (paired, exact)")
        names = list(results)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                bb, cc, p = mcnemar(results[a]["six"], results[b]["six"])
                better = a if bb > cc else (b if cc > bb else "tie")
                print(f"  {a} vs {b}:  {a} only {bb}, {b} only {cc}, "
                      f"p={p:.4f}  ->  {better}")

    for name, r in results.items():
        for m in r["misses"][: args.show_misses]:
            print(f"\n[{name}] {m['source']}  {m['raw']}")
            for f, v in m["wrong"].items():
                print(f"    {f:<12} gold={v['gold']!r}  pred={v['pred']!r}")
    print(f"{'=' * 74}\n")


if __name__ == "__main__":
    main()
