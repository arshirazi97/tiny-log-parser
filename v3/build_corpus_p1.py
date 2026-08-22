#!/usr/bin/env python3
"""Sample the P1 evaluation corpus from Loghub-2.0.

New file, not an edit to anything in v3/FREEZE_P0.txt.

The corpus is drawn from templates that appear in NEITHER the Loghub 1.0 *_2k
files NOR the existing 177-line dev/test corpus, so nothing that shaped
rule_parser.py or the v2 result can reappear here.

    python v3/build_corpus_p1.py --data <loghub2-dir> --out real-eval

Writes three files:

    corpus_p1.jsonl    the raw log lines and nothing else -- this is what gets
                       labelled. No EventId, no Level, no Component: blind
                       labelling is a property of what the labeller can see,
                       and the cheapest guarantee is that Loghub's answers are
                       not in the file.
    p1_sidecar.jsonl   those same lines' Loghub columns, kept aside. Open only
                       AFTER labels are frozen, to measure agreement.
    P1_FREEZE.txt      hashes and seed. Commit before labelling.

HOLDOUT. An EventId is excluded if any of its lines' Content appears in that
system's 1.0 2k annotations, or if the selected line's template signature
matches a held line's. Content-level exclusion is the primary net; signature is
the backstop for the case where 2.0 re-tokenised a template that 1.0 also had.
"""
import argparse, csv, hashlib, json, random, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "real-eval")
from build_corpus import signature          # frozen-era helper, reused as-is

csv.field_size_limit(10_000_000)

IN_DIST = ["HDFS", "OpenStack", "Linux", "OpenSSH", "Proxifier",
           "Spark", "HealthApp", "Zookeeper", "Apache", "Hadoop"]
OOD = ["BGL", "Thunderbird", "Mac", "HPC"]

RICH = {"OpenStack", "HDFS"}                 # carry trace/status/latency
SEED = 20260822

# declared in the pre-registration BEFORE sampling
QUOTA_IN_DIST = 20                           # x 10 systems = 200
QUOTA_OOD = 25                               # x  4 systems = 100

MAX_CANDIDATES_PER_TEMPLATE = 5              # bound the raw-log fetch


def find_files(data: Path, system: str):
    csv_hits = sorted(data.glob(f"**/{system}*structured*.csv"))
    log_hits = [p for p in sorted(data.glob(f"**/{system}*.log"))
                if "templates" not in p.name]
    return (csv_hits[0] if csv_hits else None,
            log_hits[0] if log_hits else None)


def held_for(system: str, cache: Path, corpus_lines: set[str]):
    """What this system already spent: 2k Contents, plus held signatures."""
    contents, sigs = set(), set()
    c = cache / f"{system}_2k.csv"
    if c.exists():
        with c.open(errors="replace", newline="") as fh:
            for r in csv.DictReader(fh):
                v = (r.get("Content") or "").strip()
                if v:
                    contents.add(v)
    lg = cache / f"{system}_2k.log"
    if lg.exists():
        for line in lg.read_text(errors="replace").splitlines():
            line = line.strip()
            if line:
                sigs.add(signature(line))
    for line in corpus_lines:
        sigs.add(signature(line))
    return contents, sigs


def pick(system, csv_path, log_path, quota, held_contents, held_sigs, rng):
    """One line per unseen EventId, up to quota. Longest instance wins."""
    by_event = defaultdict(list)
    spent = set()
    with csv_path.open(errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            eid = r.get("EventId")
            lid = r.get("LineId")
            if not eid or not lid or not lid.isdigit():
                continue
            if (r.get("Content") or "").strip() in held_contents:
                spent.add(eid)
                continue
            if len(by_event[eid]) < MAX_CANDIDATES_PER_TEMPLATE:
                by_event[eid].append((int(lid), r))

    fresh = [e for e in by_event if e not in spent]
    fresh.sort()
    rng.shuffle(fresh)
    if not fresh:
        return [], len(spent), 0

    # over-draw: signature holdout will reject some, and short lines are dull
    draw = fresh[:quota * 3]
    want = {}
    for eid in draw:
        for lid, r in by_event[eid]:
            want[lid] = (eid, r)

    raw_by_lid = {}
    if log_path and log_path.exists():
        pending = dict(want)
        with log_path.open(errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                if i in pending:
                    raw_by_lid[i] = line.rstrip("\n").rstrip()
                    del pending[i]
                    if not pending:
                        break
    else:
        print(f"  {system}: no raw log -- cannot build blind lines", file=sys.stderr)
        return [], len(spent), 0

    best = {}
    for lid, (eid, r) in want.items():
        raw = raw_by_lid.get(lid, "").strip()
        if not raw or signature(raw) in held_sigs:
            continue
        if eid not in best or len(raw) > len(best[eid][1]):
            best[eid] = (lid, raw, r)

    chosen, sig_rejects = [], len(draw) - len(best)
    for eid in draw:
        if len(chosen) >= quota:
            break
        if eid in best:
            lid, raw, r = best[eid]
            chosen.append((eid, lid, raw, r))
    return chosen, len(spent), sig_rejects


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="Loghub-2.0 directory")
    ap.add_argument("--out", default="real-eval")
    ap.add_argument("--cache", default="real-eval/.cache")
    args = ap.parse_args()
    out, cache = Path(args.out), Path(args.cache)

    corpus_lines = set()
    for name in ("corpus_dev.jsonl", "corpus_test.jsonl"):
        p = out / name
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip():
                    corpus_lines.add(json.loads(line)["raw"])
    print(f"existing corpus: {len(corpus_lines)} lines held out", file=sys.stderr)

    data = Path(args.data)
    rng = random.Random(SEED)
    corpus, sidecar, missing = [], [], []

    for slice_name, systems, quota in (("in-dist", IN_DIST, QUOTA_IN_DIST),
                                       ("ood", OOD, QUOTA_OOD)):
        for system in systems:
            c, l = find_files(data, system)
            if not c:
                missing.append(system)
                print(f"{system:12} no structured CSV -- skipped", file=sys.stderr)
                continue
            hc, hs = held_for(system, cache, corpus_lines)
            chosen, spent, sig_rej = pick(system, c, l, quota, hc, hs, rng)
            print(f"{system:12} {len(chosen):3}/{quota} picked  "
                  f"({spent} templates already spent, {sig_rej} signature rejects)",
                  file=sys.stderr)
            for eid, lid, raw, r in chosen:
                rid = hashlib.sha1(raw.encode()).hexdigest()[:12]
                corpus.append({"id": rid, "source": system, "slice": slice_name,
                               "stratum": "rich" if system in RICH else "sparse",
                               "raw": raw})
                sidecar.append({"id": rid, "source": system, "line_id": lid,
                                "event_id": eid,
                                "event_template": r.get("EventTemplate"),
                                "columns": {k: v for k, v in r.items()
                                            if k not in ("EventId", "EventTemplate")}})

    seen, uniq_c, uniq_s = set(), [], []
    by_id = {s["id"]: s for s in sidecar}
    for rec in corpus:
        if rec["id"] in seen:
            continue
        seen.add(rec["id"])
        uniq_c.append(rec)
        uniq_s.append(by_id[rec["id"]])

    # shuffle so labelling order does not group by format and anchor the labeller
    order = list(range(len(uniq_c)))
    rng.shuffle(order)
    uniq_c = [uniq_c[i] for i in order]
    uniq_s = [uniq_s[i] for i in order]

    for name, rows in (("corpus_p1.jsonl", uniq_c), ("p1_sidecar.jsonl", uniq_s)):
        p = out / name
        with p.open("w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(f"wrote {p}: {len(rows)} records", file=sys.stderr)

    digests = {n: hashlib.sha256((out / n).read_bytes()).hexdigest()
               for n in ("corpus_p1.jsonl", "p1_sidecar.jsonl")}
    ind = sum(1 for r in uniq_c if r["slice"] == "in-dist")
    (out / "P1_FREEZE.txt").write_text(
        "# P1 corpus freeze\n"
        f"seed\t{SEED}\n"
        f"in-dist\t{ind}\nood\t{len(uniq_c) - ind}\n"
        + "".join(f"{h}  {n}\n" for n, h in digests.items())
        + (f"# MISSING: {', '.join(missing)}\n" if missing else ""))

    print(f"\n{len(uniq_c)} lines ({ind} in-dist / {len(uniq_c)-ind} ood)",
          file=sys.stderr)
    if missing:
        print(f"MISSING SYSTEMS: {', '.join(missing)}", file=sys.stderr)
    print("Commit corpus_p1.jsonl and P1_FREEZE.txt BEFORE labelling.",
          file=sys.stderr)
    print("Do not open p1_sidecar.jsonl until labels are frozen.", file=sys.stderr)


if __name__ == "__main__":
    main()
