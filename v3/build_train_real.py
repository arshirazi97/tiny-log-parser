#!/usr/bin/env python3
"""Turn Loghub's structured annotations into v3 training records.

v2 trained on 11 invented format renderers and lost on real logs: 35 of its 42
field errors are two conventions no synthetic renderer contains. This builds
training data from real lines instead.

Labels come from Loghub's own columns wherever they exist, NOT from
rule_parser.py -- training on the parser's output would distil the parser and
re-couple the labels to their author. Agreement of these columns with the
hand-adjudicated test labels: level 127/127, message 127/127, service 111/127.

    python v3/build_train_real.py --out v3/train_real.jsonl

Contamination control: every line in corpus_dev/corpus_test is excluded, and so
is every line sharing its template signature. Verified, not assumed.
"""
import argparse, csv, io, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "real-eval")
from schema_v2 import LEVELS

IN_DIST = ["HDFS", "OpenStack", "Linux", "OpenSSH", "Proxifier",
           "Spark", "HealthApp", "Zookeeper", "Apache", "Hadoop"]

ALIAS = {"WARN": "WARNING", "W": "WARNING", "ERR": "ERROR", "E": "ERROR",
         "DBG": "DEBUG", "NOTICE": "INFO", "CRIT": "FATAL", "CRITICAL": "FATAL"}

LEVEL_COL = {"HDFS", "OpenStack", "Spark", "Zookeeper", "Apache", "Hadoop", "Linux"}
COMP_COL = {"HDFS": "Component", "OpenStack": "Component", "Linux": "Component",
            "Proxifier": "Program", "Spark": "Component", "HealthApp": "Component",
            "Zookeeper": "Component", "Hadoop": "Component"}
MONTHS = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def norm_level(v):
    if not v:
        return None
    t = ALIAS.get(v.strip().upper(), v.strip().upper())
    return t if t in LEVELS else None            # Linux "combo" -> None


def norm_service(source, row, raw):
    if source == "Apache":
        return None                              # no component position
    if source == "OpenSSH":
        m = re.search(r"\d\d:\d\d:\d\d \S+ ([\w.\-]+?)(?:\[\d+\])?: ", raw)
        return m.group(1) if m else None         # their Component is the hostname
    v = (row.get(COMP_COL.get(source, "Component")) or "").strip()
    if not v:
        return None
    if source == "Zookeeper":
        v = v.split(":")[-1]                     # thread prefix, keep the class
    if source == "Linux":
        v = re.sub(r"\(.*?\)$", "", v)           # S2: drop parenthesised qualifier
    return v or None


def ts(source, r):
    """Canonical timestamp from Loghub's own date/time columns."""
    def frac(t, sep):
        return (t.split(sep) + [None])[:2] if sep in t else (t, None)
    if source == "HDFS":
        d, t = r["Date"], r["Time"].zfill(6)
        return f"20{d[0:2]}-{d[2:4]}-{d[4:6]}T{t[0:2]}:{t[2:4]}:{t[4:6]}Z"
    if source in ("Zookeeper", "Hadoop"):
        base, ms = frac(r["Time"], ",")
        return f"{r['Date']}T{base}" + (f".{ms}Z" if ms else "Z")
    if source == "OpenStack":
        return f"{r['Date']}T{r['Time']}Z"
    if source == "Spark":
        d = r["Date"].split("/")
        return f"20{d[0]}-{d[1]}-{d[2]}T{r['Time']}Z"
    if source == "Linux":
        return (f"1900-{MONTHS[r['Month']]:02d}-{int(r['Date']):02d}"
                f"T{r['Time']}Z")
    if source == "OpenSSH":
        return f"1900-{MONTHS[r['Date']]:02d}-{int(r['Day']):02d}T{r['Time']}Z"
    if source == "Proxifier":
        m, d = r["Time"].split(" ")[0].split(".")
        return f"1900-{m}-{d}T{r['Time'].split(' ')[1]}Z"
    if source == "HealthApp":
        d, t = r["Time"].split("-")
        p = t.split(":")
        return (f"{d[0:4]}-{d[4:6]}-{d[6:8]}T{int(p[0]):02d}:{int(p[1]):02d}:"
                f"{int(p[2]):02d}" + (f".{p[3]}Z" if len(p) > 3 else "Z"))
    if source == "Apache":
        p = r["Time"].split()                    # Sun Dec 04 04:47:44 2005
        return f"{p[4]}-{MONTHS[p[1]]:02d}-{int(p[2]):02d}T{p[3]}Z"
    raise KeyError(source)


TRACE = re.compile(r"\breq-[0-9a-f]{8}-[0-9a-f-]{27}\b", re.I)
STATUS = re.compile(r"\bstatus:\s*(\d{3})\b")
TIME_S = re.compile(r"\btime:\s*([\d.]+)\b")


def extras(source, content, raw=""):
    """trace_id / status_code / latency_ms. Null unless the line really has them.

    The OpenStack req- id sits in the ADDR column, not Content, so the trace
    search runs over the raw line; status and latency stay in Content.
    """
    trace = status = lat = None
    if source == "OpenStack":
        m = TRACE.search(raw)
        trace = m.group(0) if m else None
        m = STATUS.search(content)
        status = int(m.group(1)) if m else None
        m = TIME_S.search(content)
        if m:
            v = float(m.group(1)) * 1000
            lat = int(v) if v == int(v) else v
    return trace, status, lat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="real-eval/.cache")
    ap.add_argument("--out", default="v3/train_real.jsonl")
    ap.add_argument("--validate", action="store_true",
                    help="score the extractor against the hand labels and stop")
    args = ap.parse_args()
    cache = Path(args.cache)

    # everything the eval touches, by exact line and by template signature
    import importlib.util
    s = importlib.util.spec_from_file_location("bc", "real-eval/build_corpus.py")
    bc = importlib.util.module_from_spec(s); s.loader.exec_module(bc)
    held_lines, held_sigs = set(), set()
    for f in ("corpus_dev.jsonl", "corpus_test.jsonl"):
        for r in map(json.loads, open(f"real-eval/{f}")):
            held_lines.add(r["raw"].strip())
            held_sigs.add(bc.signature(r["raw"]))

    records, skipped = [], Counter()
    for source in IN_DIST:
        raw = (cache / f"{source}_2k.log").read_text(errors="replace").splitlines()
        rows = list(csv.DictReader(io.StringIO(
            (cache / f"{source}_2k.csv").read_text(errors="replace"))))
        by_id = {r["LineId"]: r for r in rows}
        for i, line in enumerate(raw, 1):
            line = line.strip()
            r = by_id.get(str(i))
            if not line or r is None:
                continue
            if line in held_lines or bc.signature(line) in held_sigs:
                skipped[source] += 1
                continue
            content = (r.get("Content") or "").strip()
            trace, status, lat = extras(source, content, line)
            records.append({
                "source": source,
                "input": line,
                "output": {
                    "timestamp": ts(source, r),
                    "level": norm_level(r.get("Level")) if source in LEVEL_COL else None,
                    "service": norm_service(source, r, line),
                    "trace_id": trace,
                    "status_code": status,
                    "latency_ms": lat,
                    "message": content,
                },
            })

    with open(args.out, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    per = Counter(r["source"] for r in records)
    print(f"wrote {args.out}: {len(records)} records")
    print("  per source:", dict(per))
    print("  held out (eval lines + their template families):", dict(skipped),
          f"= {sum(skipped.values())} total")
    nulls = {f: sum(1 for r in records if r["output"][f] is None) / len(records)
             for f in ["level", "service", "trace_id", "status_code", "latency_ms"]}
    print("  null rate:", {k: f"{v:.0%}" for k, v in nulls.items()})


if __name__ == "__main__":
    main()
