#!/usr/bin/env python3
"""Turn a plain .log file into a corpus `predict.py` can consume.

`predict.py` reads {id, raw, source, stratum} and writes those keys straight
back out, so all four have to exist even when nothing is being scored.

    python real-eval/messy_corpus.py messy.log -o real-eval/corpus_messy.jsonl

There are no gold labels here and none are invented. This produces a corpus for
a SIDE-BY-SIDE comparison, not an accuracy measurement -- `score_arms.py` needs
labels and is deliberately not part of this path.
"""
import argparse, hashlib, json, re, sys

# a rough shape label, so the comparison table is readable at a glance
SHAPES = [
    ("json",    re.compile(r'^\s*\{')),
    ("apache",  re.compile(r'^\S+ \S+ \S+ \[[^\]]+\] "')),
    ("logfmt",  re.compile(r'(^|\s)(ts|time)=\S+')),
    ("bracket", re.compile(r'^\[')),
    ("syslog",  re.compile(r'^(<\d+>)?[A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2}')),
    ("java",    re.compile(r'^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[.,]\d+')),
]


def shape(line):
    for name, pat in SHAPES:
        if pat.search(line):
            return name
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logfile")
    ap.add_argument("-o", "--out", default="real-eval/corpus_messy.jsonl")
    a = ap.parse_args()

    lines = [l.rstrip("\n") for l in open(a.logfile, errors="replace")]
    lines = [l for l in lines if l.strip()]
    if not lines:
        sys.exit(f"{a.logfile} has no non-blank lines")

    with open(a.out, "w") as fh:
        for l in lines:
            fh.write(json.dumps({
                "id": hashlib.sha1(l.encode()).hexdigest()[:12],
                "raw": l,
                "source": shape(l),
                "stratum": "messy",
            }) + "\n")

    counts = {}
    for l in lines:
        counts[shape(l)] = counts.get(shape(l), 0) + 1
    print(f"wrote {a.out}  ({len(lines)} lines)")
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
