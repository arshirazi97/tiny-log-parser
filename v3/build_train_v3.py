#!/usr/bin/env python3
"""Build the v3 training set: real Loghub-2.0 lines + targeted synthetic.

    python3 v3/generate_v3.py --n 5000 --out v3/synth_v3.jsonl
    python3 v3/build_train_v3.py --data loghub2 --synth v3/synth_v3.jsonl \
        --out v3/train_v3.jsonl

Mix is 75% real / 25% synthetic, declared in v3/PREREGISTRATION_P2.md before any
data existed.

WHERE THE LABELS COME FROM, and the coupling that implies:

  real 75%   `rule_parser.py`. Loghub-2.0's structured CSV carries only
             LineId, Content, EventId, EventTemplate -- no Level, no Component --
             so timestamp/level/service cannot come from Loghub. Gate A measured
             this teacher at 84.4% against independent human labels, so the model
             is being distilled from something wrong ~16% of the time and cannot
             exceed it. Stated, not worked around.

  synth 25%  exact by construction. Validated: `rule_parser.py` agrees with these
             labels on 100% of records under score_arms.eq, so the two halves
             teach one convention rather than two.

CONTAMINATION. A line is excluded if it appears in corpus_p1 / corpus_dev /
corpus_test, if it shares an EventId with any line that does, or if its template
signature matches one. Verified and reported before writing, never assumed.
"""
import argparse, csv, json, random, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "real-eval")
import importlib.util
from build_corpus import signature

csv.field_size_limit(10_000_000)

IN_DIST = ["HDFS", "OpenStack", "Linux", "OpenSSH", "Proxifier",
           "Spark", "HealthApp", "Zookeeper", "Apache", "Hadoop"]
FIELDS = ["timestamp", "level", "service", "trace_id",
          "status_code", "latency_ms", "message"]


def load_parser():
    s = importlib.util.spec_from_file_location("rp", "real-eval/rule_parser.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def find_files(data: Path, system: str):
    c = sorted(data.glob(f"**/{system}*structured*.csv"))
    l = [p for p in sorted(data.glob(f"**/{system}*.log")) if "templates" not in p.name]
    return (c[0] if c else None, l[0] if l else None)


def held(system: str, cache: Path, corpus_lines, corpus_sigs):
    """Content values and signatures this system has already spent on eval."""
    contents = set()
    c = cache / f"{system}_2k.csv"
    if c.exists():
        with c.open(errors="replace", newline="") as fh:
            for r in csv.DictReader(fh):
                v = (r.get("Content") or "").strip()
                if v:
                    contents.add(v)
    sigs = set(corpus_sigs)
    lg = cache / f"{system}_2k.log"
    if lg.exists():
        for line in lg.read_text(errors="replace").splitlines():
            if line.strip():
                sigs.add(signature(line.strip()))
    return contents, sigs


def draw(system, csv_path, log_path, cap, held_contents, held_sigs,
         corpus_lines, rp, rng, per_system):
    """Up to `cap` lines per unseen EventId, labelled by the parser."""
    by_event, spent = defaultdict(list), set()
    with csv_path.open(errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            eid, lid = r.get("EventId"), r.get("LineId")
            if not eid or not lid or not lid.isdigit():
                continue
            if (r.get("Content") or "").strip() in held_contents:
                spent.add(eid)
                continue
            if len(by_event[eid]) < cap * 3:
                by_event[eid].append(int(lid))

    want = {}
    for eid, lids in by_event.items():
        if eid in spent:
            continue
        for lid in rng.sample(lids, min(len(lids), cap)):
            want[lid] = eid
    if not want or not (log_path and log_path.exists()):
        return [], len(spent), 0, 0

    picked, rejected, unparsed = [], 0, 0
    seen_inputs = set()
    budget = per_system
    with log_path.open(errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            if i not in want:
                continue
            raw = line.rstrip("\n").rstrip().strip()
            if raw in seen_inputs:                 # Loghub repeats lines verbatim
                continue
            if not raw or raw in corpus_lines or signature(raw) in held_sigs:
                rejected += 1
                continue
            out = rp.parse_line(raw)[0]
            if out is None or out.get("timestamp") is None:
                unparsed += 1
                continue
            seen_inputs.add(raw)
            picked.append({"source": system, "family": "real", "input": raw,
                           "output": {f: out.get(f) for f in FIELDS}})
            if len(picked) >= budget:
                break
    return picked, len(spent), rejected, unparsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="Loghub-2.0 directory")
    ap.add_argument("--synth", default="v3/synth_v3.jsonl")
    ap.add_argument("--out", default="v3/train_v3.jsonl")
    ap.add_argument("--cache", default="real-eval/.cache")
    ap.add_argument("--eval-dir", default="real-eval")
    ap.add_argument("--cap", type=int, default=40, help="lines per EventId")
    ap.add_argument("--per-system", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260823)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    rp = load_parser()

    ev = Path(a.eval_dir)
    corpus_lines, corpus_sigs = set(), set()
    for name in ("corpus_p1.jsonl", "corpus_dev.jsonl", "corpus_test.jsonl"):
        p = ev / name
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            if line.strip():
                raw = json.loads(line)["raw"]
                corpus_lines.add(raw)
                corpus_sigs.add(signature(raw))
    print(f"eval lines held out: {len(corpus_lines)} "
          f"({len(corpus_sigs)} signatures)\n", file=sys.stderr)

    data = Path(a.data)
    real, missing = [], []
    for system in IN_DIST:
        c, l = find_files(data, system)
        if not c:
            missing.append(system)
            print(f"{system:12} no structured CSV -- skipped", file=sys.stderr)
            continue
        hc, hs = held(system, Path(a.cache), corpus_lines, corpus_sigs)
        rows, spent, rej, unp = draw(system, c, l, a.cap, hc, hs,
                                     corpus_lines, rp, rng, a.per_system)
        real += rows
        print(f"{system:12} {len(rows):5} lines   "
              f"({spent} templates spent, {rej} contamination rejects, "
              f"{unp} unparsed by the teacher)", file=sys.stderr)

    synth = [json.loads(l) for l in Path(a.synth).read_text().splitlines() if l.strip()]

    # 75/25 -- trim whichever side overshoots rather than resampling
    n_syn = min(len(synth), len(real) // 3)
    n_real = min(len(real), n_syn * 3)
    rng.shuffle(real); rng.shuffle(synth)
    mixed = real[:n_real] + [{"source": "synthetic", "family": s["family"],
                              "input": s["input"], "output": s["output"]}
                             for s in synth[:n_syn]]
    rng.shuffle(mixed)

    # verify, do not assume
    bad = [r for r in mixed if r["input"] in corpus_lines
           or signature(r["input"]) in corpus_sigs]
    print(f"\ncontamination check: {len(bad)} eval lines present in training set",
          file=sys.stderr)
    if bad:
        sys.exit("ABORT: contamination detected, refusing to write")

    with open(a.out, "w") as f:
        for r in mixed:
            f.write(json.dumps(r) + "\n")

    fam = Counter(r["family"] for r in mixed)
    src = Counter(r["source"] for r in mixed if r["source"] != "synthetic")
    print(f"\nwrote {a.out}: {len(mixed)} records "
          f"({n_real} real / {n_syn} synthetic = "
          f"{n_real/len(mixed):.0%}/{n_syn/len(mixed):.0%})")
    for k, v in fam.most_common():
        print(f"  {k:32} {v:6}  {v/len(mixed):5.1%}")
    print(f"  real per source: {dict(src)}")
    nulls = {f: sum(1 for r in mixed if r["output"][f] is None) / len(mixed)
             for f in ("level", "service", "trace_id", "status_code", "latency_ms")}
    print("  null rate:", {k: f"{v:.0%}" for k, v in nulls.items()})
    if missing:
        print(f"  MISSING SYSTEMS: {', '.join(missing)}")


if __name__ == "__main__":
    main()
