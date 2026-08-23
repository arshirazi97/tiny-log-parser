#!/usr/bin/env python3
"""Write the P3 scoring subsets, and say why each line was removed.

`ADJUDICATION.md` and `build_corpus.py` are frozen, so neither is edited here.
Two independent reasons make a scored line uninformative about the v3
intervention, and each gets its own subset so the effect of removing it is
visible rather than folded into the headline:

  contaminated  a training line shares this line's template signature.
                `build_corpus.signature` misses these: its `<HEX>` rule,
                `[0-9a-fA-F]{8,}`, also matches plain DECIMAL runs of 8+
                digits, so `equator 89317210` becomes <HEX> while
                `equator 13586755`'s 7-digit neighbours become <N>. Two lines
                off the same template get different signatures according to
                how many digits their numbers happen to have. `sig_fixed`
                below requires at least one a-f letter before calling a token
                hex; everything else is byte-identical to the frozen rules.

  s1b           the disputed Zookeeper rule (PREREGISTRATION_AMENDED.md:621).
                ADJUDICATION.md:84 says take the class before `@<line>`; the
                annotator labelled those lines null on a blind second pass.
                Every arm follows S1b, so these measure the rule, not the arm.

    python real-eval/subsets_p3.py                 # report only
    python real-eval/subsets_p3.py --write         # emit the subset files
"""
import argparse, json, re, sys

LABELS = "real-eval/spotcheck_p1_adjudicated.jsonl"
TRAIN = "v3/train_v3.jsonl"

# frozen rules from build_corpus.py:34, with the hex/decimal collision fixed
_SIG = [
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), '<IP>'),
    (re.compile(r'\b(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{8,}\b'), '<HEX>'),
    (re.compile(r'\b\d+\b'), '<N>'),
    (re.compile(r'/[\w./\-]+'), '<PATH>'),
    (re.compile(r'\s+'), ' '),
]
# `[QuorumPeer[myid=1]/0:0:0:0:0:0:0:0:2181:Follower@89]` nests a bracket, so a
# [^\]] span cannot reach the class. Anchor on the `Class@<line>]` tail instead.
# Yields 13, matching the count in PREREGISTRATION_AMENDED.md:622.
S1B = re.compile(r'[A-Za-z_$][\w$]*@\d+\]')


def sig_fixed(line):
    for pat, rep in _SIG:
        line = pat.sub(rep, line)
    return line.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--labels", default=LABELS)
    ap.add_argument("--train", default=TRAIN)
    a = ap.parse_args()

    labels = [json.loads(l) for l in open(a.labels) if l.strip()]
    train_sigs = {}
    for l in open(a.train):
        r = json.loads(l)
        train_sigs.setdefault(sig_fixed(r["input"]), 0)
        train_sigs[sig_fixed(r["input"])] += 1

    contaminated, s1b = {}, []
    for r in labels:
        n = train_sigs.get(sig_fixed(r["raw"]))
        if n:
            contaminated[r["id"]] = n
        if S1B.search(r["raw"]):
            s1b.append(r["id"])

    print(f"scored lines: {len(labels)}")
    print(f"\ncontaminated ({len(contaminated)}) -- template also in {a.train}")
    for r in labels:
        if r["id"] in contaminated:
            print(f"  {r['id']}  {r['source']:<10} n_train={contaminated[r['id']]:<4}"
                  f" {r['raw'][:72]}")
    print(f"\ns1b-disputed ({len(s1b)}) -- gold departs from ADJUDICATION.md:84")
    for r in labels:
        if r["id"] in s1b:
            print(f"  {r['id']}  {r['source']:<10} gold={r['label']['service']!r:<24}"
                  f" {r['raw'][:56]}")

    drop = set(contaminated) | set(s1b)
    subsets = {
        "clean":        set(contaminated),
        "nos1b":        set(s1b),
        "clean_nos1b":  drop,
    }
    print()
    for name, rm in subsets.items():
        keep = [r for r in labels if r["id"] not in rm]
        path = a.labels.replace(".jsonl", f"_{name}.jsonl")
        print(f"{name:<14} n={len(keep):<4} (-{len(rm)})  {path}")
        if a.write:
            with open(path, "w") as fh:
                for r in keep:
                    fh.write(json.dumps(r) + "\n")
    if not a.write:
        print("\n(report only -- pass --write to emit the files)")


if __name__ == "__main__":
    main()
