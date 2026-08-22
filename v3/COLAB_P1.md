# P1: build the blind evaluation corpus (Colab, CPU)

Everything here is I/O — downloading Loghub-2.0, counting, and sampling a few
hundred lines. **Runtime -> Change runtime type -> CPU.** A GPU is wasted here;
the pod comes back for P2, if P2 happens.

What comes out: 300 raw log lines nobody has labelled yet, and the numbers
needed to check that the pre-registration's finding 4 is real.

Order: fetch -> measure -> **stop and read** -> sample. The stop is not
optional. The corpus should not be drawn on measurements that disagree with
what the amendment claims.

---

### Cell 1 — clone, and fetch the Loghub 1.0 annotations

```python
!git clone -q https://github.com/arshirazi97/tiny-log-parser.git
%cd tiny-log-parser
!python v3/fetch_loghub1.py
```

`.cache/` is gitignored, so a fresh clone has none of the 1.0 files. Both
scripts below need them: the sampler reads the 2k `Content` values to decide
which 2.0 templates are already spent, and the measurement script reads the 2k
column schema to decide whether a system's header carries a year or a real
level. Loghub-2.0 annotates neither.

Expect 14 lines of `log=ok  csv=ok`.

---

### Cell 2 — download Loghub-2.0 (~966 MB, 10–20 min)

```bash
%%bash
mkdir -p loghub2 && cd loghub2
for S in HDFS OpenStack Linux OpenSSH Proxifier Spark HealthApp Zookeeper \
         Apache Hadoop BGL Thunderbird Mac HPC; do
  echo "== $S"
  wget -q --show-progress "https://zenodo.org/records/8275861/files/$S.zip?download=1" -O $S.zip
  shasum -a 256 $S.zip >> ../v3/SOURCES_2.txt
  unzip -oq $S.zip && rm $S.zip
done
wc -l ../v3/SOURCES_2.txt
```

Zenodo record `8275861`, 14 per-system zips. Each is hashed **before** it is
unpacked, so `SOURCES_2.txt` records what was actually downloaded rather than
what survived unzipping. Should end at 14 lines.

This is the step that cannot run on a laptop with 2.8 GB free.

---

### Cell 3 — recompute finding 4

```python
!python v3/measure_loghub2.py --data loghub2 --out v3/MEASUREMENTS_P1.txt
```

**Stop and read the output before running Cell 4.**

The amendment's finding 4 was measured in a session that no longer exists. This
is the check. Verified locally on four systems, all matching:

| system | annotated lines | header recovery |
|---|---|---|
| Linux | 23,921 | 100.0% |
| Apache | 51,978 | 100.0% |
| Proxifier | 21,320 (11 templates) | 100.0% |
| HPC | 429,988 | — |

Mac should read 100,314 lines and 626 templates.

Header recovery is measured under collapsed whitespace, and must be: Loghub-2.0
normalises runs of spaces inside `Content`, so a literal comparison reads 81.6%
on Linux where the true figure is 100.0%. All 4,406 apparent mismatches there
are doubled spaces.

If a trap count disagrees materially with finding 4, **stop**. Record the
disagreement; do not edit the amendment to match. The mine-don't-generate
decision and the trap upweighting both rest on those counts.

---

### Cell 4 — sample the corpus

```python
!python v3/build_corpus_p1.py --data loghub2 --out real-eval
```

200 in-distribution (10 systems × 20) + 100 OOD (4 systems × 25), seed
`20260822`, one line per unseen `EventId`, declared in
`PREREGISTRATION_AMENDED.md` before the corpus existed.

Quotas are ceilings. **Proxifier will fall well short** — it has 11 templates in
all of Loghub-2.0 and the existing corpus already spent 6. That is the dead end
recorded in the amendment, not a bug. Shortfalls are reported in
`P1_FREEZE.txt` and are not backfilled from template-rich systems, which would
silently reweight the corpus.

---

### Cell 5 — bundle and download

```python
!cd /content/tiny-log-parser && zip -j /content/p1_out.zip \
    real-eval/corpus_p1.jsonl real-eval/p1_sidecar.jsonl real-eval/P1_FREEZE.txt \
    v3/MEASUREMENTS_P1.txt v3/SOURCES_2.txt
from google.colab import files; files.download('/content/p1_out.zip')
```

Unzip into the repo: the first three into `real-eval/`, the last two into
`v3/`. Commit all five.

---

## Then, on your own machine

**Do not open `p1_sidecar.jsonl`.** It holds Loghub's `Content`, which is the
gold `message` field, and its `EventTemplate`. Reading it before labelling
contaminates the thing P1 exists to measure. It is opened after labels are
frozen, to report agreement.

```bash
python real-eval/label.py real-eval/corpus_p1.jsonl     # -> labels_p1.jsonl
```

Resumable. `?` shows the schema, `<` steps back a field, `!<note>` flags a line
as ambiguous instead of guessing. 300 lines × 7 fields, against
`ADJUDICATION.md`.

Then Gate A: score the frozen `rule_parser.py` against those labels.

- **~92%** — the parser generalises to templates nobody tuned it on, and the
  README's headline claim is evidenced for the first time. v3 proceeds.
- **75–80%** — the published 92.1% was fitting. Stop, correct the README,
  build nothing on top of it.

Both outcomes are worth P1 on their own, whether or not v3 is ever trained.
