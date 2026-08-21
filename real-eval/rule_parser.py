#!/usr/bin/env python3
"""Hand-written deterministic parser -- the third arm of the real-log eval.

This is the arm the project was missing. The synthetic test set could always be
solved by inverting generate.py, so a 100% there proved nothing about the model.
On real logs no generator exists, and this parser has to be written by hand
against formats a person actually looked at. If the fine-tune beats it on unseen
sources, the model has earned its place. If it doesn't, that is also a result.

Format is detected FROM THE LINE. The `source` field in the corpus is never
read -- the model doesn't get told which log family a line came from, so this
doesn't either.

Built against corpus_dev.jsonl only. Rules follow ADJUDICATION.md.

    python real-eval/rule_parser.py --corpus real-eval/corpus_dev.jsonl
    python real-eval/rule_parser.py --corpus real-eval/corpus_dev.jsonl --show 5
"""
import argparse, json, re, sys
from collections import Counter

FIELDS = ["timestamp", "level", "service", "trace_id",
          "status_code", "latency_ms", "message"]

MONTHS = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}

# Rule L2. Anything not in here is not a level.
LEVELS = {
    "TRACE": "TRACE", "DEBUG": "DEBUG", "INFO": "INFO", "NOTICE": "INFO",
    "WARN": "WARNING", "WARNING": "WARNING", "ERR": "ERROR", "ERROR": "ERROR",
    "FATAL": "FATAL", "CRIT": "FATAL", "CRITICAL": "FATAL",
}

# Ambiguities hit while writing this. Each one wants a rule in ADJUDICATION.md
# before the test set is unfrozen. Recorded rather than silently decided.
OPEN_QUESTIONS = []


def lvl(tok):
    return LEVELS.get(tok.strip().upper()) if tok else None


def iso(y, mo, d, h, mi, s, frac=None):
    """T2: no timezone in the line means UTC. T3: keep sub-second as given."""
    base = f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}"
    return f"{base}.{frac}Z" if frac else f"{base}Z"


def rec(**kw):
    r = {f: None for f in FIELDS}
    r.update(kw)
    return r


# --------------------------------------------------------------------------
# One matcher per format. Order matters: the most specific prefix wins.
# --------------------------------------------------------------------------

def m_openstack(l):
    # S4: leading token is a log FILENAME, not a service. Service is the logger
    # after the PID. F2: trace_id keeps the req- prefix.
    m = re.match(
        r"^\S+\.log\S*\s+(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)\.(\d+)\s+"
        r"(\d+)\s+(\w+)\s+(\S+)\s+(\[(req-[0-9a-f-]{36})[^\]]*\]\s*)?(.*)$", l)
    if not m:
        return None
    y, mo, d, h, mi, s, frac, _pid, lv, logger, _b, req, msg = m.groups()
    lat = None
    t = re.search(r"\btime:\s*([\d.]+)", msg)        # F4: seconds -> ms, no rounding
    if t:
        lat = float(t.group(1)) * 1000
    st = re.search(r'"\s+(\d{3})\s+\d+', msg) or re.search(r"\bstatus:\s*(\d{3})", msg)
    return rec(timestamp=iso(int(y), int(mo), int(d), int(h), int(mi), int(s), frac),
               level=lvl(lv), service=logger, trace_id=req,
               status_code=int(st.group(1)) if st else None,
               latency_ms=lat, message=msg.strip())


def m_zookeeper(l):
    # "2015-08-20 17:14:24,000 - INFO  [thread:Class@line] - message"
    m = re.match(r"^(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d),(\d+) - (\w+)\s+"
                 r"\[(.+?)\] - (.*)$", l)
    if not m:
        return None
    y, mo, d, h, mi, s, frac, lv, thread, msg = m.groups()
    # S1 wants the logger. Zookeeper buries it in the thread bracket, and the
    # bracket itself contains ':' separators, so "before the first :" does not
    # apply cleanly here.
    # ADJUDICATION S1b: the class immediately before @<line>, not the thread.
    cls = re.search(r"([A-Za-z_$][\w$]*)@\d+$", thread)
    if not cls:
        OPEN_QUESTIONS.append(("zookeeper-bracket-without-@line", l[:70]))
    return rec(timestamp=iso(int(y), int(mo), int(d), int(h), int(mi), int(s), frac),
               level=lvl(lv), service=cls.group(1) if cls else None,
               message=msg.strip())


def m_hadoop(l):
    # "2015-10-18 18:02:02,104 INFO [thread] fully.qualified.Logger: message"
    m = re.match(r"^(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d),(\d+) (\w+)\s+"
                 r"\[(.+?)\] ([\w.$]+): (.*)$", l)
    if not m:
        return None
    y, mo, d, h, mi, s, frac, lv, _thread, logger, msg = m.groups()
    return rec(timestamp=iso(int(y), int(mo), int(d), int(h), int(mi), int(s), frac),
               level=lvl(lv), service=logger, message=msg.strip())


def m_hdfs(l):
    # T4: "081110 222512" is yymmdd hhmmss, two-digit year -> 20xx.
    m = re.match(r"^(\d\d)(\d\d)(\d\d) (\d\d)(\d\d)(\d\d) (\d+) (\w+) ([\w.$]+): (.*)$", l)
    if not m:
        return None
    y, mo, d, h, mi, s, _pid, lv, logger, msg = m.groups()
    return rec(timestamp=iso(2000 + int(y), int(mo), int(d), int(h), int(mi), int(s)),
               level=lvl(lv), service=logger, message=msg.strip())
    # F3: blk_* in the message is a data id, not a trace id -> stays null.


def m_spark(l):
    # T4: "17/06/09" is yy/mm/dd.
    m = re.match(r"^(\d\d)/(\d\d)/(\d\d) (\d\d):(\d\d):(\d\d) (\w+) ([\w.$]+): (.*)$", l)
    if not m:
        return None
    y, mo, d, h, mi, s, lv, logger, msg = m.groups()
    return rec(timestamp=iso(2000 + int(y), int(mo), int(d), int(h), int(mi), int(s)),
               level=lvl(lv), service=logger, message=msg.strip())


def m_apache(l):
    # "[Sun Dec 04 06:01:42 2005] [notice] message"  -- S3: no service position.
    m = re.match(r"^\[\w{3} (\w{3}) +(\d+) (\d\d):(\d\d):(\d\d) (\d{4})\] \[(\w+)\] (.*)$", l)
    if not m:
        return None
    mon, d, h, mi, s, y, lv, msg = m.groups()
    return rec(timestamp=iso(int(y), MONTHS[mon], int(d), int(h), int(mi), int(s)),
               level=lvl(lv), service=None, message=msg.strip())


def m_healthapp(l):
    # "20171223-22:31:59:725|Step_LSC|30002312|message"  (h:m:s not zero-padded)
    m = re.match(r"^(\d{4})(\d\d)(\d\d)-(\d+):(\d+):(\d+):(\d+)\|([^|]*)\|(\d+)\|(.*)$", l)
    if not m:
        return None
    y, mo, d, h, mi, s, frac, comp, _pid, msg = m.groups()
    return rec(timestamp=iso(int(y), int(mo), int(d), int(h), int(mi), int(s), frac),
               level=None,                       # L1: no level token present
               service=comp or None, message=msg.strip())


def m_proxifier(l):
    # "[10.30 16:49:10] chrome.exe *64 - host:port close, ..."  T1: no year.
    m = re.match(r"^\[(\d\d)\.(\d\d) (\d\d):(\d\d):(\d\d)\] (\S+?)(?: \*\d+)? - (.*)$", l)
    if not m:
        return None
    mo, d, h, mi, s, proc, msg = m.groups()
    # ADJUDICATION F5: a connection lifetime is not the latency of the event.
    return rec(timestamp=iso(1900, int(mo), int(d), int(h), int(mi), int(s)),
               level=None, service=proc, message=msg.strip())


def m_syslog(l):
    # "Dec 10 10:54:29 LabSZ sshd[24868]: msg" / "Jul 27 14:41:59 combo kernel: msg"
    # T1: no year in the line -> 1900 sentinel. L1: no level token -> null.
    m = re.match(r"^(\w{3}) +(\d+) (\d\d):(\d\d):(\d\d) (\S+) ([^:\[]+?)"
                 r"(?:\((\w+)\))?(?:\[(\d+)\])?: (.*)$", l)
    if not m or m.group(1) not in MONTHS:
        return None
    mon, d, h, mi, s, _host, proc, _pam, _pid, msg = m.groups()
    # S2: drop the PAM qualifier and the PID, keep the process name.
    return rec(timestamp=iso(1900, MONTHS[mon], int(d), int(h), int(mi), int(s)),
               level=None, service=proc.strip(), message=msg.strip())


MATCHERS = [m_openstack, m_zookeeper, m_hadoop, m_hdfs, m_spark,
            m_apache, m_healthapp, m_proxifier, m_syslog]


def parse_line(raw):
    for m in MATCHERS:
        out = m(raw)
        if out is not None:
            return out, m.__name__[2:]
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="real-eval/corpus_dev.jsonl")
    ap.add_argument("--show", type=int, default=0, help="print N parsed examples")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if "test" in args.corpus:
        sys.exit("Refusing to touch the test corpus. Build against dev only.")

    rows = [json.loads(l) for l in open(args.corpus) if l.strip()]
    results, unmatched = [], []
    hit_by_source = Counter()
    for r in rows:
        pred, which = parse_line(r["raw"])
        if pred is None:
            unmatched.append(r)
        else:
            hit_by_source[r["source"]] += 1
        results.append({**r, "pred": pred, "matcher": which})

    n = len(rows)
    matched = n - len(unmatched)
    print(f"\n{'='*72}\ncoverage          {matched}/{n} = {matched/n:.1%} of lines parsed")
    print(f"{'-'*72}\nper source        (parsed / total)")
    src_total = Counter(r["source"] for r in rows)
    for s in sorted(src_total):
        print(f"  {s:<11} {hit_by_source[s]}/{src_total[s]}")

    print(f"{'-'*72}\nfield fill rate   (how often the parser emits non-null)")
    for f in FIELDS:
        v = sum(1 for x in results if x["pred"] and x["pred"][f] is not None)
        print(f"  {f:<12} {v:3}/{n}  {v/n:6.1%}")

    if unmatched:
        print(f"{'-'*72}\nUNMATCHED ({len(unmatched)}) -- these need a matcher:")
        for r in unmatched:
            print(f"  {r['source']:<11} {r['raw'][:88]}")

    if OPEN_QUESTIONS:
        print(f"{'-'*72}\nOPEN ADJUDICATION QUESTIONS -- resolve before unfreezing test:")
        grouped = {}
        for q, ex in OPEN_QUESTIONS:
            grouped.setdefault(q, []).append(ex)
        for q in sorted(grouped):
            print(f"  [{q}]  {len(grouped[q])} line(s)\n    e.g. {grouped[q][0]}")

    for x in results[: args.show]:
        print(f"\n{'-'*72}\n{x['source']} via {x['matcher']}\n  {x['raw'][:100]}")
        for f in FIELDS:
            print(f"    {f:<12} {(x['pred'] or {}).get(f)!r}")

    print(f"{'='*72}\n")
    print("NOTE: coverage is not accuracy. Scoring needs labels_dev.jsonl, and the")
    print("labels must be written WITHOUT looking at this parser's output.\n")

    if args.out:
        json.dump(results, open(args.out, "w"), indent=2)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
