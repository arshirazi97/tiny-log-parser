#!/usr/bin/env python3
"""Check that every v3 training label is derivable from its input.

    python3 v3/validate_v3.py v3/train_v3.jsonl

Port of `validate_v2.py`, which stays untouched as the v2 gate. Every check it
makes is kept. Two are corrected, because they encode `generate_v2.py`'s
conventions rather than `ADJUDICATION.md`'s, and the v3 set contains real Loghub
lines that the v2 generator could never produce.

  T3 sub-seconds. v2 required exactly three fractional digits, because every v2
  renderer emitted milliseconds. ADJUDICATION T3 says "preserve what the line
  gives ... do not pad or truncate", and HealthApp writes `20171226-8:0:4:1`,
  whose correct label ends `.1`. The rule now accepts 1-9 digits and checks
  those digits appear in the line.
    -> corrected 60 false failures on the first v3 build.

  P1/F5 prose durations. v2 flagged a null latency whenever the line contained
  took/elapsed/duration/rt/cost. Under P1 a duration in the message text IS
  null: `PM response took 2010 ms` is prose, not a field. 95 lines in the 1.0
  caches alone trip the old rule while being correctly labelled. The rule now
  fires only on an `=`-delimited field, which is a genuine structural position.
    -> corrected 7 false failures.

  Status codes additionally accept OpenStack's `status: NNN` form, which the
  parser extracts and which carries no `HTTP/1.1"`.

Neither change was made to make a dataset pass. Both are cases where the v2
validator and the frozen rulebook disagree, and the rulebook governs.
"""
import json, re, sys
from collections import Counter

TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{1,9})?Z$")   # T3
LEVELS = {"TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "FATAL"}
LVLTOK = re.compile(r"\b(TRACE|DEBUG|DBG|INFO|NOTICE|WARN|WARNING|ERROR|ERR|"
                    r"FATAL|CRIT|CRITICAL)\b", re.I)
TRACEKEY = re.compile(r"\b(x-)?trace[-_]?id\b|\btrace\s*[=:]", re.I)
NOYEAR = re.compile(r"^(<\d+>)?[A-Z][a-z]{2} [ \d]\d \d\d:\d\d:\d\d |"
                    r"^\[\d\d\.\d\d \d\d:\d\d:\d\d\] ")
STRUCT_DUR = re.compile(r"\b(took|elapsed|duration|rt|cost)\s*=")     # P1/F5


def check(rows, tag):
    fails = []

    def bad(k, row, extra=""):
        fails.append((k, row["input"][:90], extra))

    for row in rows:
        o, i = row["output"], row["input"]

        if not TS.match(o["timestamp"] or ""):
            bad("ts-format", row, o["timestamp"])
        else:
            y = int(o["timestamp"][:4])
            if (y == 1900) != bool(NOYEAR.match(i)):
                bad("sentinel-mismatch", row, f"year={y}")
            if "." in o["timestamp"]:
                frac = o["timestamp"].split(".")[1].rstrip("Z")
                if frac not in i:
                    bad("frac-not-in-line", row, frac)

        if o["level"] is not None and o["level"] not in LEVELS:
            bad("bad-level", row, str(o["level"]))

        t = o["trace_id"]
        if t is not None:
            if not (re.fullmatch(r"[0-9a-f]{32}", t)
                    or re.fullmatch(r"req-[0-9a-f-]{36}", t)):
                bad("bad-trace-shape", row, t)
            elif t not in i:
                bad("trace-not-in-line", row, t)

        if o["status_code"] is not None:
            if not ('HTTP/1.1"' in i or re.search(r"\bstatus:\s*\d{3}", i)):
                bad("status-without-context", row, str(o["status_code"]))
            elif str(o["status_code"]) not in i:
                bad("status-not-in-line", row, str(o["status_code"]))

        if o["service"] is not None and o["service"] not in i:
            bad("service-not-in-line", row, o["service"])

        if o["latency_ms"] is None and STRUCT_DUR.search(i):
            bad("latency-null-but-structural-field", row)

        if (ms := o["latency_ms"]) is not None:
            cands = [(f"{ms}ms", ms), (f"{ms / 1000:.3f}s", None),
                     (f"{ms / 1000:.3f}", None), (f"{ms / 1000:.7f}", None),
                     (str(ms), ms)]
            if isinstance(ms, int):
                cands.append((f"{ms * 1000}us", ms))
            ok = False
            for text, val in cands:
                if text not in i:
                    continue
                if val is None:
                    num = re.sub(r"[^\d.]", "", text)
                    val = float(num) * 1000 if "." in num and float(num) < 100 else None
                if val is not None and abs(val - ms) < 1e-6:
                    ok = True
                    break
            if not ok:
                bad("latency-not-derivable", row, str(ms))

        msg = re.sub(r"\s+", " ", o["message"] or "").strip()
        if msg and msg not in re.sub(r"\s+", " ", i):
            bad("message-not-in-line", row, msg[:40])

    print(f"\n{tag}: {len(rows)} rows -> {len(fails)} failures")
    for k, v in Counter(f[0] for f in fails).most_common():
        print(f"  {k:<34} {v}")
    for f in fails[:6]:
        print(f"   e.g. [{f[0]}] {f[1]}  {f[2]}")
    return fails


def main():
    paths = sys.argv[1:] or ["v3/train_v3.jsonl"]
    total = 0
    for p in paths:
        rows = [json.loads(l) for l in open(p) if l.strip()]
        total += len(check(rows, p))
        print(f"  duplicate inputs: {len(rows) - len(set(r['input'] for r in rows))}")
        fam = Counter(r.get("family", "?") for r in rows)
        print(f"  families: {dict(fam)}")
    print(f"\n{'PASS' if total == 0 else 'FAIL'}: {total} total failures")
    sys.exit(0 if total == 0 else 1)


if __name__ == "__main__":
    main()
