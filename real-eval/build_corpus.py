#!/usr/bin/env python3
"""Build a frozen real-world log corpus for evaluating tiny-log-parser.

Downloads Loghub 2k samples, deduplicates by template signature (so we get
distinct log shapes rather than 40 copies of the same line), stratifies into
RICH (schema-exercising) and SPARSE (abstention-testing) lines, and splits
into a dev set (iterate against this) and a test set (touch once, at the end).

Usage:
    python build_corpus.py --out .
"""
import argparse, hashlib, json, random, re, sys, urllib.request
from pathlib import Path

LOGHUB = "https://raw.githubusercontent.com/logpai/loghub/master/{d}/{d}_2k.log"

# stratum assignment is by source, based on measured field presence
RICH_SOURCES = ["OpenStack", "HDFS"]
SPARSE_SOURCES = ["Apache", "Linux", "OpenSSH", "Zookeeper",
                  "Hadoop", "Spark", "HealthApp", "Proxifier"]

# how many distinct-template lines to draw from each source
QUOTA = {
    "OpenStack": 30, "HDFS": 20,
    "Apache": 15, "Linux": 20, "OpenSSH": 20, "Zookeeper": 15,
    "Hadoop": 15, "Spark": 15, "HealthApp": 15, "Proxifier": 15,
}

SEED = 20260820

# --- template signature: collapse variable content so near-identical lines dedupe
_SIG = [
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), '<IP>'),
    (re.compile(r'\b[0-9a-fA-F]{8,}\b'), '<HEX>'),
    (re.compile(r'\b\d+\b'), '<N>'),
    (re.compile(r'/[\w./\-]+'), '<PATH>'),
    (re.compile(r'\s+'), ' '),
]


def signature(line: str) -> str:
    s = line
    for pat, rep in _SIG:
        s = pat.sub(rep, s)
    return s.strip()


def fetch(source: str, cache: Path) -> list[str]:
    f = cache / f"{source}_2k.log"
    if not f.exists():
        url = LOGHUB.format(d=source)
        print(f"  downloading {source} ...", file=sys.stderr)
        urllib.request.urlretrieve(url, f)
    raw = f.read_text(errors="replace").splitlines()
    return [l.strip() for l in raw if l.strip()]


def distinct_templates(lines: list[str], k: int, rng: random.Random) -> list[str]:
    """Pick k lines with distinct template signatures, preferring longer/richer ones."""
    buckets: dict[str, list[str]] = {}
    for l in lines:
        buckets.setdefault(signature(l), []).append(l)
    keys = sorted(buckets)
    rng.shuffle(keys)
    out = []
    for key in keys:
        if len(out) >= k:
            break
        # take the longest instance of each template - more field content to parse
        out.append(max(buckets[key], key=len))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    ap.add_argument("--cache", default=".")
    args = ap.parse_args()
    out, cache = Path(args.out), Path(args.cache)
    out.mkdir(parents=True, exist_ok=True)

    rng = random.Random(SEED)
    records = []
    for source in RICH_SOURCES + SPARSE_SOURCES:
        lines = fetch(source, cache)
        picked = distinct_templates(lines, QUOTA[source], rng)
        stratum = "rich" if source in RICH_SOURCES else "sparse"
        print(f"{source:12} {len(picked):3} lines  ({len(lines)} available, stratum={stratum})",
              file=sys.stderr)
        for l in picked:
            records.append({
                "id": hashlib.sha1(l.encode()).hexdigest()[:12],
                "source": source,
                "stratum": stratum,
                "raw": l,
            })

    # dedupe across sources, then shuffle so labelling order doesn't group by format
    seen, uniq = set(), []
    for r in records:
        if r["id"] not in seen:
            seen.add(r["id"])
            uniq.append(r)
    rng.shuffle(uniq)

    # dev = first 50, test = rest. Split AFTER shuffle so both are stratum-mixed.
    dev, test = uniq[:50], uniq[50:]
    for name, rows in (("dev", dev), ("test", test)):
        p = out / f"corpus_{name}.jsonl"
        with p.open("w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        digest = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        rich = sum(1 for r in rows if r["stratum"] == "rich")
        print(f"\n{name}: {len(rows)} lines ({rich} rich / {len(rows)-rich} sparse)")
        print(f"  {p}  sha256={digest}")

    (out / "CORPUS_FREEZE.txt").write_text(
        "\n".join(
            f"{n}\t{hashlib.sha256((out/f'corpus_{n}.jsonl').read_bytes()).hexdigest()}"
            for n in ("dev", "test")
        ) + f"\nseed\t{SEED}\n"
    )
    print("\nFrozen. Commit CORPUS_FREEZE.txt now, before labelling.")


if __name__ == "__main__":
    main()
