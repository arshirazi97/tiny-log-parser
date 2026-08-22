#!/usr/bin/env python3
"""Fill the gold `message` field from Loghub-2.0's `Content` column.

    python real-eval/fill_message_from_loghub.py          # --dry-run first

Run this AFTER labelling is finished, never before: `p1_sidecar.jsonl` holds
Loghub's `Content`, which is the answer for `message`, and seeing it during
labelling would contaminate the other fields too.

Why this field and no other. Loghub-2.0's structured CSV carries exactly four
columns -- LineId, Content, EventId, EventTemplate. `Content` is a third-party
annotation of the message body, produced by the logpai authors years before
this project and with no knowledge of this schema. For `message` that is better
provenance than a human retyping the line. For every other field Loghub-2.0
annotates nothing, which is why timestamp, level and service are hand-labelled.

Provenance is recorded per record as `label_source`, so the split is legible in
the data rather than only in a document:

    {"timestamp": "hand", "level": "hand", "service": "hand",
     "trace_id": "hand", "status_code": "hand", "latency_ms": "hand",
     "message": "loghub-2.0:Content"}
"""
import argparse, json, sys
from pathlib import Path

HAND = ["timestamp", "level", "service", "trace_id", "status_code", "latency_ms"]


def load(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="real-eval")
    ap.add_argument("--apply", action="store_true",
                    help="write the file; without it, report only")
    a = ap.parse_args()
    out = Path(a.out)
    lab_p, side_p = out / "labels_p1.jsonl", out / "p1_sidecar.jsonl"

    if not lab_p.exists():
        sys.exit("no labels_p1.jsonl -- nothing to fill")
    labels, side = load(lab_p), {r["id"]: r for r in load(side_p)}

    filled = missing = overwritten = 0
    for r in labels:
        s = side.get(r["id"])
        if s is None:
            missing += 1
            continue
        content = (s.get("columns", {}).get("Content") or "").strip()
        if not content:
            missing += 1
            continue
        if r["label"].get("message") not in (None, ""):
            overwritten += 1
        r["label"]["message"] = content
        # preserve whatever provenance the record already carries; only the
        # message field's source is settled by this script
        src = r.get("label_source") or {f: "hand" for f in HAND}
        src["message"] = "loghub-2.0:Content"
        r["label_source"] = src
        filled += 1

    print(f"labels        {len(labels)}")
    print(f"message filled from Loghub  {filled}")
    print(f"no sidecar Content          {missing}")
    if overwritten:
        print(f"NOTE: {overwritten} record(s) already had a message; it was replaced.")

    if not a.apply:
        print("\ndry run -- re-run with --apply to write")
        return
    with lab_p.open("w") as f:
        for r in labels:
            f.write(json.dumps(r) + "\n")
    print(f"\nwrote {lab_p}")


if __name__ == "__main__":
    main()
