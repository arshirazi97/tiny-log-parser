#!/usr/bin/env python3
"""Fetch the Loghub 1.0 2k annotations into real-eval/.cache.

`.cache/` is gitignored, so a fresh clone -- Colab, a pod, a new laptop -- has
none of these. Both P1 scripts need them: the sampler reads the 2k `Content`
values to decide which Loghub-2.0 templates are already spent, and the
measurement script reads the 2k column schema to decide whether a system's
header carries a year or a real level. Loghub-2.0 annotates neither.

    python v3/fetch_loghub1.py

Downloads `<System>_2k.log` and `<System>_2k.log_structured.csv` for all 14
systems, saving the latter as `<System>_2k.csv` -- the name the existing
scripts already expect.
"""
import argparse, sys, urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/logpai/loghub/master/{s}/{s}_2k.log"
SYSTEMS = ["HDFS", "OpenStack", "Linux", "OpenSSH", "Proxifier", "Spark",
           "HealthApp", "Zookeeper", "Apache", "Hadoop",
           "BGL", "Thunderbird", "Mac", "HPC"]


def get(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size:
        return True
    try:
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        dest.unlink(missing_ok=True)
        print(f"  FAILED {url}: {e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="real-eval/.cache")
    args = ap.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    missing = []
    for s in SYSTEMS:
        log = get(BASE.format(s=s), cache / f"{s}_2k.log")
        csv_ = get(BASE.format(s=s) + "_structured.csv", cache / f"{s}_2k.csv")
        print(f"{s:12} log={'ok' if log else 'MISSING'}  csv={'ok' if csv_ else 'MISSING'}")
        if not (log and csv_):
            missing.append(s)

    if missing:
        print(f"\nincomplete: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    print(f"\n{len(SYSTEMS)} systems cached in {cache}")


if __name__ == "__main__":
    main()
