#!/usr/bin/env python3
"""Side-by-side two or more arms on the same corpus, with no gold labels.

    python real-eval/compare_arms.py --corpus real-eval/corpus_messy.jsonl \
        v3=real-eval/preds_messy_v3.jsonl gemini=real-eval/preds_messy_gemini.jsonl

Prints every line, every arm's six fields, and marks the fields the arms
disagree on. Then a summary: how often they agree per field, and where each
arm emitted a non-null value the other did not.

Agreement is NOT accuracy. With no labels, two arms agreeing can both be wrong
and a disagreement says only that one of them is. Use this to find the
interesting lines, then read them yourself.
"""
import argparse, json, re, sys

FIELDS = ["timestamp", "level", "service", "trace_id", "status_code", "latency_ms"]


def norm(v):
    """Same comparison rules as score_arms.eq, minus the gold-label half."""
    if isinstance(v, str):
        return re.sub(r"\s+", " ", v).strip()
    return v


def eq(a, b):
    a, b = norm(a), norm(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(float(a) - float(b)) < 1e-9
    for x, y in ((a, b), (b, a)):
        if isinstance(x, str) and isinstance(y, (int, float)):
            try:
                return abs(float(x) - float(y)) < 1e-9
            except ValueError:
                return False
    return a == b


def show(v, w):
    s = "null" if v is None else (v if isinstance(v, str) else json.dumps(v))
    return (s[: w - 1] + "…") if len(s) > w else s.ljust(w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--width", type=int, default=30)
    ap.add_argument("--only-disagreements", action="store_true")
    ap.add_argument("arms", nargs="+", help="name=path/to/preds.jsonl")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.corpus) if l.strip()]
    arms, preds = [], {}
    for spec in a.arms:
        if "=" not in spec:
            sys.exit(f"expected name=path, got {spec!r}")
        name, path = spec.split("=", 1)
        arms.append(name)
        preds[name] = {r["id"]: r.get("pred")
                       for r in (json.loads(l) for l in open(path) if l.strip())}

    w = a.width
    agree = {f: [0, 0] for f in FIELDS}          # [all-agree, comparable]
    nonnull = {n: {f: 0 for f in FIELDS} for n in arms}
    unparseable = {n: 0 for n in arms}
    shown = 0

    for i, r in enumerate(rows, 1):
        got = {}
        for n in arms:
            p = preds[n].get(r["id"])
            if not isinstance(p, dict):
                unparseable[n] += 1
                p = None
            got[n] = p

        diff = set()
        for f in FIELDS:
            vals = [got[n].get(f) if got[n] is not None else "__none__" for n in arms]
            agree[f][1] += 1
            if all(eq(vals[0], v) for v in vals[1:]):
                agree[f][0] += 1
            else:
                diff.add(f)
            for n in arms:
                if got[n] is not None and got[n].get(f) is not None:
                    nonnull[n][f] += 1

        if a.only_disagreements and not diff:
            continue
        shown += 1
        print(f"\n[{i}] {r.get('source','?')}  {r['id']}"
              f"{'   (all arms agree)' if not diff else ''}")
        print(f"    {r['raw'][:110]}")
        print(f"    {'':<14}" + "".join(n.ljust(w) for n in arms))
        for f in FIELDS:
            mark = "≠" if f in diff else " "
            cells = "".join(
                show(got[n].get(f) if got[n] is not None else "UNPARSEABLE", w)
                for n in arms)
            print(f"  {mark} {f:<14}{cells}")

    n = len(rows)
    print(f"\n{'=' * (18 + w * len(arms))}")
    print(f"corpus {a.corpus}   n={n}   shown={shown}")
    print(f"{'-' * (18 + w * len(arms))}")
    print(f"{'field':<18}{'arms agree':<14}")
    for f in FIELDS:
        ok, tot = agree[f]
        print(f"  {f:<16}{f'{ok}/{tot}':<10}{ok / tot:>7.1%}")
    full = sum(1 for r in rows
               if all(eq((preds[arms[0]].get(r["id"]) or {}).get(f),
                         (preds[n].get(r["id"]) or {}).get(f))
                      for f in FIELDS for n in arms[1:]))
    print(f"\n  all six fields identical on {full}/{n} lines ({full / n:.1%})")
    print(f"{'-' * (18 + w * len(arms))}")
    print(f"{'non-null emitted':<18}" + "".join(x.ljust(w) for x in arms))
    for f in FIELDS:
        print(f"  {f:<16}" + "".join(
            f"{nonnull[arm][f]}/{n}".ljust(w) for arm in arms))
    if any(unparseable.values()):
        print("\nunparseable: " + "  ".join(
            f"{arm}={unparseable[arm]}" for arm in arms))


if __name__ == "__main__":
    main()
