"""Check that every generated label is actually derivable from its input.

The dataset is only "correct by construction" if the renderer really emits what
the label claims. It did not, at first: four renderers assigned a trace_id in
the record and then never printed it, giving 4,304 rows whose gold trace_id
appeared nowhere in the line. That is an unlearnable label, and it would have
been trained on. This runs before any GPU time is spent.

    python validate_v2.py train_v2.jsonl test_v2.jsonl
"""
import json
import re
import sys
from collections import Counter

TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{3})?Z$")
LEVELS = {"TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "FATAL"}
LVLTOK = re.compile(r"\b(TRACE|DEBUG|DBG|INFO|NOTICE|WARN|WARNING|ERROR|ERR|"
                    r"FATAL|CRIT|CRITICAL)\b", re.I)
TRACEKEY = re.compile(r"\b(x-)?trace[-_]?id\b|\btrace\s*[=:]", re.I)

# the three renderers that legitimately carry no year
NOYEAR = re.compile(r"^(<\d+>)?[A-Z][a-z]{2} [ \d]\d \d\d:\d\d:\d\d |^\[\d\d\.\d\d \d\d:\d\d:\d\d\] ")


def check(rows, tag):
    fails = []

    def bad(k, row, extra=""):
        fails.append((k, row["input"][:90], extra))

    for row in rows:
        o, i = row["output"], row["input"]

        if not TS.match(o["timestamp"]):
            bad("ts-format", row, o["timestamp"])
        y = int(o["timestamp"][:4])
        # the 1900 sentinel must correspond to a genuinely year-less format
        if (y == 1900) != bool(NOYEAR.match(i)):
            bad("sentinel-mismatch", row, f"year={y}")
        if "." in o["timestamp"]:
            frac = o["timestamp"].split(".")[1][:3]
            if frac not in i:
                bad("frac-not-in-line", row, frac)

        if o["level"] is not None and o["level"] not in LEVELS:
            bad("bad-level", row, str(o["level"]))
        if o["level"] is None:
            # a level word inside the message text is not a level (spec: do not
            # infer from wording), so search the line with the message removed.
            # trace-key names ("trace-id", "X-Trace-Id") contain "trace" and
            # would otherwise read as the TRACE level -- strip them too.
            outside = i.replace(o["message"], " ")
            if t := o["trace_id"]:
                outside = outside.replace(t, " ")
            outside = TRACEKEY.sub(" ", outside)
            m = LVLTOK.search(outside)
            if m:
                bad("null-level-but-token", row, m.group())

        t = o["trace_id"]
        if t is not None:
            if not (re.fullmatch(r"[0-9a-f]{32}", t)
                    or re.fullmatch(r"req-[0-9a-f-]{36}", t)):
                bad("bad-trace-shape", row, t)
            elif t not in i:
                bad("trace-not-in-line", row, t)
        if o["status_code"] is not None and 'HTTP/1.1"' not in i:
            bad("status-without-http", row)
        if o["service"] is not None and o["service"] not in i:
            bad("service-not-in-line", row, o["service"])
        if o["latency_ms"] is None and re.search(r"\b(took|elapsed|duration|rt|cost)\s*[= ]", i):
            bad("latency-null-but-field", row)
        if (ms := o["latency_ms"]) is not None:
            # the value must be recoverable from some rendering in the line
            cands = [f"{ms}ms", f"{ms / 1000:.3f}s", f"{ms / 1000:.3f}",
                     f"{ms / 1000:.7f}", str(ms)]
            if isinstance(ms, int):
                cands.append(f"{ms * 1000}us")
            if not any(c in i for c in cands):
                bad("latency-not-in-line", row, str(ms))
        msg = re.sub(r"\s+", " ", o["message"]).strip()
        if msg and msg not in re.sub(r"\s+", " ", i):
            bad("message-not-in-line", row, msg[:40])

    print(f"\n{tag}: {len(rows)} rows -> {len(fails)} failures")
    for k, v in Counter(f[0] for f in fails).most_common():
        print(f"  {k:<24} {v}")
    for f in fails[:5]:
        print(f"   e.g. [{f[0]}] {f[1]}  {f[2]}")
    return fails


def main():
    paths = sys.argv[1:] or ["train_v2.jsonl", "test_v2.jsonl"]
    sets, total = {}, 0
    for p in paths:
        rows = [json.loads(l) for l in open(p)]
        total += len(check(rows, p))
        sets[p] = set(r["input"] for r in rows)
        print(f"  duplicate inputs: {len(rows) - len(sets[p])}")
    if len(paths) == 2:
        a, b = sets[paths[0]], sets[paths[1]]
        print(f"\ntrain/test input overlap: {len(a & b)}")
    print(f"\n{'PASS' if total == 0 else 'FAIL'}: {total} total failures")
    sys.exit(0 if total == 0 else 1)


if __name__ == "__main__":
    main()
