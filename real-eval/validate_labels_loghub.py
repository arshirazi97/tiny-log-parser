#!/usr/bin/env python3
"""Cross-check our hand-adjudicated labels against LogHub's own annotations.

The objection this answers: our labels, our rule parser and the training data
all trace back to one person's rulebook, so agreement between them proves
nothing. LogHub publishes `*_2k.log_structured.csv` next to every raw log --
parsed by the logpai authors, years before this project, with no knowledge of
our schema. For `level` and `service` that is genuinely independent evidence.

    python real-eval/validate_labels_loghub.py --labels real-eval/labels_test.jsonl
    python real-eval/validate_labels_loghub.py --show-agree      # not just misses

What it CANNOT establish: timestamp, trace_id, status_code, latency_ms and
message have no counterpart in their schema. Two of seven fields is not the
whole label set -- but `level` is the field the abstention result rests on.

Their parse is positional and imperfect; three quirks are handled explicitly:

  Linux     the "Level" column holds the hostname ("combo"), not a level. Any
            value outside the level vocabulary is read as level-absent.
  Zookeeper "Component" carries a thread prefix
            ("...:2181:FastLeaderElection"); the class is the last ":" token.
  Apache    no Component column at all, and OpenSSH / Proxifier / HealthApp
            have no Level column -- absence of the column is evidence FOR our
            null, not missing data.
"""
import argparse, csv, io, json, re, sys, urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, ".")
from schema_v2 import LEVELS

RAW = "https://raw.githubusercontent.com/logpai/loghub/master/{d}/{d}_2k.log"
CSV = RAW + "_structured.csv"

# column holding the level, and the one holding the emitting component
LEVEL_COL = {"HDFS": "Level", "OpenStack": "Level", "Spark": "Level",
             "Zookeeper": "Level", "Apache": "Level", "Hadoop": "Level",
             "Linux": "Level"}          # Linux value is validated, see above
COMP_COL = {"HDFS": "Component", "OpenStack": "Component", "Linux": "Component",
            "OpenSSH": "Component", "Proxifier": "Program", "Spark": "Component",
            "HealthApp": "Component", "Zookeeper": "Component",
            "Hadoop": "Component"}      # Apache absent -> service is null

ALIAS = {"WARN": "WARNING", "W": "WARNING", "ERR": "ERROR", "E": "ERROR",
         "DBG": "DEBUG", "NOTICE": "INFO", "CRIT": "FATAL", "CRITICAL": "FATAL"}


def norm_level(v):
    """Their token -> our enum. None when it is not a level at all."""
    if not v:
        return None
    t = ALIAS.get(v.strip().upper(), v.strip().upper())
    return t if t in LEVELS else None


def norm_comp(source, v):
    if not v:
        return None
    v = v.strip()
    if source == "Zookeeper":       # "...:2181:FastLeaderElection" -> class
        v = v.split(":")[-1]
    return v or None


def fetch(url, path):
    if not path.exists():
        print(f"  downloading {path.name} ...", file=sys.stderr)
        urllib.request.urlretrieve(url, path)
    return path.read_text(errors="replace")


def load_source(source, cache):
    """{raw line -> [structured row]}. A line appearing twice maps to both."""
    raw = fetch(RAW.format(d=source), cache / f"{source}_2k.log").splitlines()
    text = fetch(CSV.format(d=source), cache / f"{source}_2k.csv")
    rows = list(csv.DictReader(io.StringIO(text)))
    by_id = {r["LineId"]: r for r in rows}
    out = defaultdict(list)
    for i, line in enumerate(raw, 1):
        r = by_id.get(str(i))
        if r is not None:
            out[line.strip()].append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="real-eval/labels_test.jsonl")
    ap.add_argument("--cache", default="real-eval/.cache")
    ap.add_argument("--show-agree", action="store_true")
    args = ap.parse_args()

    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    labels = [json.loads(l) for l in open(args.labels) if l.strip()]

    tables, tally, disagree, unmatched = {}, defaultdict(lambda: [0, 0]), [], []
    for row in labels:
        src = row["source"]
        if src not in tables:
            tables[src] = load_source(src, cache)
        hits = tables[src].get(row["raw"].strip(), [])
        if not hits:
            unmatched.append(row)
            continue

        ours = row["label"]
        # level: no column for this source means their schema says these lines
        # carry no level, which is evidence for our null rather than absence
        theirs_lvl = (norm_level(hits[0].get(LEVEL_COL[src], ""))
                      if src in LEVEL_COL else None)
        theirs_svc = (norm_comp(src, hits[0].get(COMP_COL[src], ""))
                      if src in COMP_COL else None)

        for field, theirs in (("level", theirs_lvl), ("service", theirs_svc)):
            ok = ours[field] == theirs
            tally[(src, field)][1] += 1
            tally[(src, field)][0] += ok
            if not ok:
                disagree.append({"id": row["id"], "source": src, "field": field,
                                 "ours": ours[field], "loghub": theirs,
                                 "raw": row["raw"][:88]})
            elif args.show_agree:
                print(f"  ok  {src:<10} {field:<8} {ours[field]!r}")

    n = len(labels) - len(unmatched)
    print(f"\n{'=' * 78}\nlabels {args.labels}   matched {n}/{len(labels)} "
          f"lines to a LogHub row")
    print(f"{'-' * 78}\n{'source':<12}{'level':>18}{'service':>18}")
    for src in sorted({s for s, _ in tally}):
        cells = ""
        for f in ("level", "service"):
            good, tot = tally[(src, f)]
            cells += f"{f'{good}/{tot}' if tot else '-':>18}"
        print(f"{src:<12}{cells}")
    for f in ("level", "service"):
        good = sum(v[0] for (s, ff), v in tally.items() if ff == f)
        tot = sum(v[1] for (s, ff), v in tally.items() if ff == f)
        print(f"{'TOTAL ' + f:<12}{f'{good}/{tot}  ({good/tot:.1%})':>36}"
              if tot else "")

    if disagree:
        print(f"{'-' * 78}\n{len(disagree)} disagreements\n")
        for d in disagree:
            print(f"  [{d['source']}] {d['field']}   ours={d['ours']!r}   "
                  f"loghub={d['loghub']!r}\n      {d['raw']}")
    if unmatched:
        print(f"{'-' * 78}\n{len(unmatched)} lines matched no LogHub row:")
        for r in unmatched[:10]:
            print(f"  [{r['source']}] {r['raw'][:88]}")
    print(f"{'=' * 78}\n")


if __name__ == "__main__":
    main()
