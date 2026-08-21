#!/usr/bin/env python3
"""Hand-label a frozen log corpus against the 7-field canonical schema.

Run this BEFORE running either system on the corpus. Labelling after seeing
model output anchors you to it and invalidates the whole exercise.

    python label.py corpus_dev.jsonl          # -> labels_dev.jsonl
    python label.py corpus_test.jsonl         # -> labels_test.jsonl

Resumable: re-run to continue where you stopped.

Per field: type a value, or press Enter for null (field genuinely absent).
Commands at any prompt:
    ?           show the schema + adjudication reminders
    !<note>     flag this line as ambiguous with a note, skip it
    <           go back one field
    q           save and quit
"""
import json, sys
from pathlib import Path

FIELDS = ["timestamp", "level", "service", "trace_id",
          "status_code", "latency_ms", "message"]

HELP = """
  timestamp    ISO-8601 UTC, e.g. 2015-07-29T17:41:44.747Z
               T1  no year in the line      -> use year 1900
               T2  no timezone              -> assume UTC, suffix Z
               T3  sub-second               -> keep exactly ("',747" -> ".747")
               T4  081110 222512 = yymmdd hhmmss;  17/06/09 = yy/mm/dd -> 20xx
  level        TRACE DEBUG INFO WARNING ERROR FATAL
               L1  no level token           -> null
               L1b an HTTP status code does NOT imply a level -> null
               L3  a level word inside the message text is not a level
               WARN->WARNING notice->INFO err->ERROR crit->FATAL
  service      S1  logger in its own position -> full dotted path, whole
               S1b logger inside a thread bracket -> class before "@line"
                   [SessionTracker:ZooKeeperServer@325] -> ZooKeeperServer
               S2  syslog process, drop (pam) qualifier and [pid]
               S3  no service position -> null. Never invent a placeholder.
  trace_id     F2  keep the "req-" prefix
               F3  block/job/session ids and PIDs are NOT trace ids -> null
  status_code  integer HTTP status only, else null
  latency_ms   F4  seconds -> ms, do not round (0.2477829 -> 247.7829)
               F5  a configured timeout or a connection lifetime is NOT a
                   latency -> null
  message      M1b keep the remainder verbatim; values you put in other
                   fields stay in the message text

  Enter = null.   /<text> on the message field = from that text to end of line.
"""


def load(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    corpus_path = Path(sys.argv[1])
    rows = load(corpus_path)
    out_path = corpus_path.parent / corpus_path.name.replace("corpus_", "labels_")
    amb_path = corpus_path.parent / corpus_path.name.replace("corpus_", "ambiguous_")

    done = {}
    if out_path.exists():
        done = {r["id"]: r for r in load(out_path)}
    flagged = set()
    if amb_path.exists():
        flagged = {r["id"] for r in load(amb_path)}

    todo = [r for r in rows if r["id"] not in done and r["id"] not in flagged]
    print(f"{len(done)} labelled, {len(flagged)} flagged, {len(todo)} remaining.\n")

    out_fh = out_path.open("a")
    amb_fh = amb_path.open("a")

    for n, row in enumerate(todo, 1):
        print("=" * 78)
        print(f"[{n}/{len(todo)}]  {row['source']}  ({row['stratum']})")
        print("-" * 78)
        print(row["raw"])
        print("-" * 78)
        print(f"  ({len(done) + n}/{len(rows)} of the corpus labelled)")

        label, i, aborted = {}, 0, None
        while i < len(FIELDS):
            f = FIELDS[i]
            try:
                v = input(f"  {f:12}> ").strip()
            except (EOFError, KeyboardInterrupt):
                aborted = "quit"
                break
            if v == "?":
                print(HELP)
                continue
            if v == "q":
                aborted = "quit"
                break
            if v == "<":
                i = max(0, i - 1)
                continue
            if v.startswith("!"):
                aborted = v[1:].strip() or "ambiguous"
                break
            if f == "message" and v.startswith("/"):
                # anchor: take the raw line from the first occurrence of <text>
                # to its end. You choose where the message starts; the copying
                # is mechanical, so no typos land in the gold.
                anchor = v[1:]
                if anchor and anchor in row["raw"]:
                    v = row["raw"][row["raw"].index(anchor):].strip()
                    print(f"    -> {v}")
                else:
                    print("    anchor not found in the line, try again")
                    continue
            label[f] = None if v == "" else v
            i += 1

        if aborted == "quit":
            print("\nSaved. Re-run to continue.")
            break
        if aborted:
            amb_fh.write(json.dumps({**row, "note": aborted}) + "\n")
            amb_fh.flush()
            print(f"  flagged: {aborted}\n")
            continue

        # light coercion so the verifier compares like with like
        for f in ("status_code",):
            if label.get(f) is not None:
                try: label[f] = int(label[f])
                except ValueError: pass
        for f in ("latency_ms",):
            if label.get(f) is not None:
                try: label[f] = float(label[f])
                except ValueError: pass

        out_fh.write(json.dumps({**row, "label": label}) + "\n")
        out_fh.flush()
        print()

    out_fh.close(); amb_fh.close()
    print(f"\nlabels -> {out_path}")
    print(f"flagged -> {amb_path}   (resolve these, add a rule to ADJUDICATION.md, re-run)")


if __name__ == "__main__":
    main()
