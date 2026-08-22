#!/usr/bin/env python3
"""Recompute the Loghub-2.0 measurements cited in PREREGISTRATION_AMENDED.md.

Those figures -- the trap candidate counts, the annotated-line totals, the
"log_format recovers the header at 100%" finding -- were measured in a Colab
session that no longer exists, and no script in the repo reproduces them. The
amendment's design decisions rest on them, so they are recomputed here and the
output is committed.

    python v3/measure_loghub2.py --data <loghub2-dir> --out v3/MEASUREMENTS_P1.txt

If a number disagrees with the amendment, that is a finding to record, not a
figure to quietly overwrite. The amendment was written against the originals.

OPERATIONALISATIONS -- stated here so a disagreement can be attributed to a
definition rather than to the data:

  header recovery   fraction of annotated rows whose Content is a non-empty
                    suffix of the raw line, comparing under collapsed
                    whitespace. This is what "the log_format regex recovered
                    the header" means in practice: everything the regex did not
                    claim as a header field is exactly Content. It is NOT a
                    re-run of Loghub's own regexes.

                    Whitespace must be collapsed or the measure is wrong:
                    Loghub-2.0 normalises runs of spaces inside Content, so
                    "SELinux:  Initializing." in the raw line is stored as
                    "SELinux: Initializing.". On Linux that alone accounts for
                    4,406 of 23,921 rows -- 81.6% raw vs 100.0% normalised.

  T1 trap           system is in YEARLESS AND Content contains a 4-digit year
                    -> gold timestamp is the 1900 sentinel while a year sits in
                    the prose.

  L3 / P1 level     system's header carries no REAL Level (see header_schema:
                    a Level column whose values never normalise into LEVELS
                    does not count) AND Content contains a severity word, in
                    any case -> gold level is null while a severity word sits
                    in the prose.

  P1 latency        non-OpenStack AND Content contains a duration -> gold
                    latency_ms is null while a duration sits in the prose.

  P1 status         non-OpenStack AND Content contains an HTTP status code in
                    a status-shaped context -> gold status_code is null.
"""
import argparse, csv, io, re, sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(10_000_000)

IN_DIST = ["HDFS", "OpenStack", "Linux", "OpenSSH", "Proxifier",
           "Spark", "HealthApp", "Zookeeper", "Apache", "Hadoop"]
OOD = ["BGL", "Thunderbird", "Mac", "HPC"]

SEVERITY = re.compile(
    r"\b(TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|ERR|SEVERE|FATAL|CRITICAL|CRIT)\b",
    re.I)      # case-insensitive: real severity words in prose are lowercase
               # ("error : connection refused", "*** info [mice.c]"). Measured
               # case-sensitively, Linux and Proxifier both read 0; the true
               # counts are 66 and 983.
YEAR = re.compile(r"\b(19|20)\d\d\b")
DURATION = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|msec|millisecond|milliseconds|s|sec|secs|second|seconds)\b",
    re.I)
STATUS_CTX = re.compile(
    r"(?:\bstatus(?:[ _-]?code)?\b\s*[:=]?\s*|HTTP/1\.[01]\"?\s+)([1-5]\d\d)\b", re.I)

WS = re.compile(r"\s+")


def norm(s: str) -> str:
    return WS.sub(" ", s).strip()


def find_files(data: Path, system: str):
    """Locate the structured CSV and the raw log for one system.

    Loghub-2.0 has moved its layout around between releases, so glob rather
    than assume. Reports what it found; a missing system is skipped, not fatal.
    """
    csv_hits = sorted(data.glob(f"**/{system}*structured*.csv"))
    log_hits = [p for p in sorted(data.glob(f"**/{system}*.log"))
                if "templates" not in p.name]
    return (csv_hits[0] if csv_hits else None,
            log_hits[0] if log_hits else None)


LEVELS = {"TRACE", "DEBUG", "INFO", "NOTICE", "WARN", "WARNING",
          "ERROR", "ERR", "SEVERE", "FATAL", "CRITICAL", "CRIT"}

# Systems whose header carries no year, so gold timestamp takes the T1 1900
# sentinel. Declared explicitly rather than sniffed.
#
# Sniffing for /(19|20)\d\d/ over the 1.0 columns fails in both directions and
# was doing so: Spark's `17/06/09` and HealthApp's `20171223-22:15:29:606` are
# real years that the pattern misses (no word boundary), which credited them
# with 748,231 T1 traps they do not have; and HDFS was credited as year-bearing
# only because a PID happened to read `1946`. HDFS does carry a year, in
# `081109` -- the right answer for the wrong reason.
#
# In-distribution entries are taken from build_train_real.py's ts(), which is
# frozen and is the authority on which systems get the 1900 sentinel. OOD
# entries are read off the 1.0 column schema: Mac is Month/Date/Time, while
# BGL and Thunderbird carry a Date and HPC an epoch.
YEARLESS = {"Linux", "OpenSSH", "Proxifier", "Mac"}


def header_schema(system: str, cache: Path):
    """Does this system's header carry a year, and a real Level?

    The year comes from the YEARLESS table above; it is declared, not sniffed.
    The level is measured: a Level column whose values normalise into LEVELS
    counts as a real level, and one whose values never do is not a level.

    Loghub-2.0's structured CSV is LineId,Content,EventId,EventTemplate only --
    it annotates the message body and the template, and drops every header
    field. So the question "does the header carry a year / a level" cannot be
    answered from 2.0 at all, and is answered from the 1.0 2k annotations,
    which are the same systems in the same formats.

    "Real Level" is deliberately stricter than "has a Level column": Linux's
    Level column holds `combo`, the hostname, which ADJUDICATION.md says is not
    a level. A column whose values never normalise into LEVELS does not count.
    """
    c = cache / f"{system}_2k.csv"
    if not c.exists():
        return None, None
    with c.open(errors="replace", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return None, None
    has_year = system not in YEARLESS
    has_level = "Level" in rows[0] and any(
        (r.get("Level") or "").strip().upper() in LEVELS for r in rows[:400])
    return has_year, has_level


def measure(system: str, csv_path: Path, log_path: Path, cache: Path, out):
    """One streaming pass over the structured CSV, joined to the raw log.

    Nothing is materialised. Loghub-2.0's largest system is Thunderbird at
    16.6M annotated lines; holding those as dicts needs several GB and OOMs a
    stock Colab CPU runtime. LineId is sequential, so the CSV and the raw log
    are walked in parallel and the join costs no memory at all.
    """
    has_year, has_level = header_schema(system, cache)
    if has_year is None:
        print(f"{system:12} no 1.0 annotations in {cache} -- traps skipped",
              file=sys.stderr)
    is_openstack = system == "OpenStack"

    templates = set()
    traps = Counter()
    n = recovered = checked = 0

    log_fh = log_path.open(errors="replace") if log_path and log_path.exists() else None
    log_pos = 0

    with csv_path.open(errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            n += 1
            eid = r.get("EventId")
            if eid:
                templates.add(eid)
            content = r.get("Content") or ""

            if has_year is not None:
                if not has_year and YEAR.search(content):
                    traps["T1_year_in_prose"] += 1
                if not has_level and SEVERITY.search(content):
                    traps["L3_severity_in_prose"] += 1
                if not is_openstack and DURATION.search(content):
                    traps["P1_duration_in_prose"] += 1
                if not is_openstack and STATUS_CTX.search(content):
                    traps["P1_status_in_prose"] += 1

            # advance the raw log to this LineId; both are in LineId order
            lid = r.get("LineId")
            if log_fh and lid and lid.isdigit():
                target = int(lid)
                line = None
                while log_pos < target:
                    line = log_fh.readline()
                    if not line:
                        break
                    log_pos += 1
                if line is not None and log_pos == target:
                    c = content.strip()
                    checked += 1
                    if c and norm(line).endswith(norm(c)):
                        recovered += 1

    if log_fh:
        log_fh.close()

    if not n:
        print(f"{system:12} EMPTY CSV -- skipped", file=sys.stderr)
        return None

    rec = f"{recovered / checked:.1%}" if checked else "n/a (no raw log)"
    print(f"\n[{system}]", file=out)
    print(f"  annotated lines      {n:,}", file=out)
    print(f"  distinct EventIds    {len(templates):,}", file=out)
    print(f"  header has year      {has_year}   (from YEARLESS table)", file=out)
    print(f"  header has Level     {has_level}   (measured on 1.0 schema)", file=out)
    print(f"  header recovery      {rec}  ({recovered:,}/{checked:,})", file=out)
    for k in ("T1_year_in_prose", "L3_severity_in_prose",
              "P1_duration_in_prose", "P1_status_in_prose"):
        print(f"  {k:24} {traps[k]:,}", file=out)
    return {"system": system, "lines": n, "templates": len(templates),
            "traps": traps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True,
                    help="directory holding the Loghub-2.0 files")
    ap.add_argument("--out", default="v3/MEASUREMENTS_P1.txt")
    ap.add_argument("--cache", default="real-eval/.cache",
                    help="Loghub 1.0 2k annotations, for the header schema")
    ap.add_argument("--systems", default="all",
                    help="comma-separated, or 'all' / 'in-dist' / 'ood'")
    args = ap.parse_args()

    sel = {"all": IN_DIST + OOD, "in-dist": IN_DIST, "ood": OOD}.get(
        args.systems, args.systems.split(","))
    data = Path(args.data)

    buf = io.StringIO()
    print("Loghub-2.0 measurements, recomputed for P1", file=buf)
    print("Operationalisations are documented in v3/measure_loghub2.py.", file=buf)

    results, missing = [], []
    for system in sel:
        c, l = find_files(data, system)
        if not c:
            missing.append(system)
            print(f"{system:12} no structured CSV found -- skipped", file=sys.stderr)
            continue
        print(f"{system:12} {c.name}", file=sys.stderr)
        r = measure(system, c, l, Path(args.cache), buf)
        if r:
            results.append(r)

    tot = Counter()
    for r in results:
        tot.update(r["traps"])
    lines = sum(r["lines"] for r in results)
    print(f"\n[TOTAL over {len(results)} systems]", file=buf)
    print(f"  annotated lines      {lines:,}", file=buf)
    for k, v in sorted(tot.items()):
        print(f"  {k:24} {v:,}", file=buf)
    if missing:
        print(f"\nMISSING (not measured): {', '.join(missing)}", file=buf)

    text = buf.getvalue()
    print(text)
    Path(args.out).write_text(text)
    print(f"\nwrote {args.out}", file=sys.stderr)
    print("Compare against PREREGISTRATION_AMENDED.md finding 4. Record any "
          "disagreement; do not edit the amendment to match.", file=sys.stderr)


if __name__ == "__main__":
    main()
