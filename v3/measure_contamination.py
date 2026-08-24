#!/usr/bin/env python3
"""Measure train/eval contamination at the level the critique actually targets.

"The fine-tuned LLM cannot be benchmarked on the exact dataset it was trained
with" is correct, and zero exact-line overlap is NOT an answer to it. A log
corpus is built from a few hundred templates instantiated thousands of times;
two lines can share a template, differ in every number, and collide as strings
never once. Exact-match de-duplication would report a clean split for a set
that is, in the way that matters, memorised.

So this measures three things, weakest to strongest:

  1. exact line overlap          -- the test that proves almost nothing
  2. identical template          -- Drain-style signature equality
  3. max near-duplicate          -- token Jaccard against EVERY training
                                    template, so a line that merely resembles
                                    one is still caught

Then it does the thing the numbers alone cannot: splits an eval set by
familiarity tier and reports accuracy per tier. If a model is reciting, it
scores well on the seen tier and falls over on the unseen one. That is a
testable claim, and it is the only real reply to the critique.

    python3 v3/measure_contamination.py
    python3 v3/measure_contamination.py --eval real-eval/corpus_heldout.jsonl
"""
import argparse, collections, importlib.util, json, math, re, sys

FIELDS = ["timestamp", "level", "service", "trace_id",
          "status_code", "latency_ms", "message"]


# The signature is build_corpus.signature -- ONE definition, shared by the
# builder's contamination guard and by this measurement. A private copy here
# is how the two drift apart and a leak goes unseen.
sys.path.insert(0, "real-eval")
from build_corpus import signature as sig


class Index:
    """Inverted index over training templates, for max-Jaccard lookup."""

    def __init__(self, inputs):
        self.sigs = list({sig(x) for x in inputs})
        self.tok = [set(s.split()) for s in self.sigs]
        self.inv = collections.defaultdict(list)
        for i, t in enumerate(self.tok):
            for w in t:
                self.inv[w].append(i)

    def maxjac(self, s):
        a = set(s.split())
        cand = collections.Counter()
        for w in a:
            for i in self.inv.get(w, ()):
                cand[i] += 1
        return max((ov / len(a | self.tok[i]) for i, ov in cand.most_common(400)),
                   default=0.0)


def norm(v):
    return re.sub(r'\s+', ' ', v).strip() if isinstance(v, str) else v


def eq(a, b):
    a, b = norm(a), norm(b)
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    if isinstance(a, str) and isinstance(b, (int, float)):
        try:
            return abs(float(a) - float(b)) < 1e-9
        except ValueError:
            return False
    return a == b


def wilson(k, n):
    if not n:
        return 0.0, 0.0
    z, p, d = 1.96, k / n, 1 + 1.96 ** 2 / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def fisher(a, b, c, d):
    n = a + b + c + d
    p0 = math.comb(a + b, a) * math.comb(c + d, c) / math.comb(n, a + c)
    tot = 0.0
    for i in range(min(a + b, a + c) + 1):
        k, l = a + c - i, d - (a - i)
        if a + b - i < 0 or k < 0 or l < 0:
            continue
        p = math.comb(a + b, i) * math.comb(c + d, k) / math.comb(n, a + c)
        if p <= p0 + 1e-12:
            tot += p
    return min(1.0, tot)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="v3/train_v3.jsonl")
    ap.add_argument("--eval", action="append", help="repeatable; default is all four")
    ap.add_argument("--preds", default="real-eval/preds_p1_v3.jsonl")
    ap.add_argument("--labels", default="real-eval/labels_p1.jsonl")
    a = ap.parse_args()

    train = [json.loads(l) for l in open(a.train) if l.strip()]
    raws = [r["input"] for r in train]
    idx = Index(raws)
    exact, tsigs = set(raws), set(idx.sigs)
    print(f"train {a.train}: {len(train)} lines, {len(tsigs)} distinct templates")

    evals = a.eval or ["real-eval/labels_p1.jsonl",
                       "real-eval/corpus_p1_unseen42.jsonl",
                       "real-eval/corpus_heldout.jsonl",
                       "messy.log"]

    print(f"\n{'='*78}\nCONTAMINATION\n{'='*78}")
    print(f"{'eval set':<40}{'exact':>8}{'same tmpl':>11}{'J>=0.9':>9}{'median J':>10}")
    for path in evals:
        if path.endswith(".log"):
            rows = [{"raw": l.strip()} for l in open(path) if l.strip()]
        else:
            rows = [json.loads(l) for l in open(path) if l.strip()]
        n = len(rows)
        ex = sum(1 for r in rows if r["raw"] in exact)
        ss = [sig(r["raw"]) for r in rows]
        st = sum(1 for s in ss if s in tsigs)
        js = sorted(idx.maxjac(s) for s in ss)
        hi = sum(1 for j in js if j >= 0.90)
        print(f"{path[-39:]:<40}{f'{ex}/{n}':>8}{f'{st}/{n}':>11}"
              f"{f'{hi}/{n}':>9}{js[n//2]:>10.2f}")

    # ---- the part that actually answers the critique -----------------------
    labels = [json.loads(l) for l in open(a.labels) if l.strip()]
    preds = {json.loads(l)["id"]: json.loads(l).get("pred")
             for l in open(a.preds) if l.strip()}
    s = importlib.util.spec_from_file_location("rp", "real-eval/rule_parser.py")
    rp = importlib.util.module_from_spec(s)
    s.loader.exec_module(rp)

    tiers = collections.defaultdict(list)
    for r in labels:
        j = idx.maxjac(sig(r["raw"]))
        tiers["seen" if j >= 0.90 else
              "similar" if j >= 0.50 else "unseen"].append(r)

    print(f"\n{'='*78}\nACCURACY BY TEMPLATE FAMILIARITY -- {a.labels}\n{'='*78}")
    print(f"{'tier':<28}{'n':>5}{'v3 exact':>11}{'95% CI':>18}{'rules':>9}")
    got = {}
    for t, lo in [("seen", "J>=0.90"), ("similar", "0.50-0.90"), ("unseen", "J<0.50")]:
        rows = tiers[t]
        n = len(rows)
        if not n:
            continue
        k = sum(1 for r in rows
                if all(eq((preds.get(r["id"]) or {}).get(f), r["label"][f])
                       for f in FIELDS))
        kr = sum(1 for r in rows
                 if all(eq(rp.parse_line(r["raw"])[0].get(f), r["label"][f])
                        for f in FIELDS))
        c = wilson(k, n)
        got[t] = (k, n)
        print(f"{t + ' (' + lo + ')':<28}{n:>5}{k/n:>10.1%}"
              f"{f'{c[0]:.1%} - {c[1]:.1%}':>18}{kr/n:>9.1%}")

    if "seen" in got and "unseen" in got:
        (sk, sn), (uk, un) = got["seen"], got["unseen"]
        p = fisher(sk, sn - sk, uk, un - uk)
        print(f"\nFisher exact, seen vs unseen: p = {p:.3f}  -> "
              f"{'no detectable memorisation effect' if p > 0.05 else 'SIGNIFICANT gap'}")
        worst = next((k for k in range(un, 0, -1)
                      if fisher(sk, sn - sk, k, un - k) < 0.05), None)
        if worst is not None:
            print(f"Power: at n={un} the unseen tier would have to fall to "
                  f"{worst}/{un} ({worst/un:.1%}) before the gap became "
                  f"detectable. A null here is weak evidence, not strong.")


if __name__ == "__main__":
    main()
