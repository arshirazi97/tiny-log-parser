# P1 — a fresh corpus, and why Gate A did not fire

P1 set out to answer one question: does `rule_parser.py`'s published **92.1%**
survive on log templates nobody tuned it against? The corpus was built, the gate
was run, and **the answer is inconclusive** — for a reason worth more than the
answer would have been.

Everything below was pre-registered in
[`v3/PREREGISTRATION_AMENDED.md`](../v3/PREREGISTRATION_AMENDED.md), including
the prediction that this exact failure could happen.

---

## The corpus

**262 lines** drawn from Loghub-2.0 (Zenodo record `8275861`, 50.4M annotated
lines across 14 systems), seed `20260822`:

- **162 in-distribution** — the ten systems the project already works on
- **100 out-of-distribution** — BGL, Thunderbird, Mac, HPC, never seen

Contamination control by `EventId`, verified rather than assumed: **zero**
raw-line overlap and **zero** template-signature overlap with the existing
177-line dev/test corpus. The sampler was tested by pointing it at the Loghub
1.0 data as if it were 2.0 — every template was correctly rejected and the draw
came back empty.

Three systems came in under quota, and two of those are structural:

| system | drawn | why |
|---|---|---|
| OpenStack | 5 / 20 | 48 templates exist in all of Loghub-2.0; the old corpus spent 43 |
| Proxifier | 1 / 20 | 11 templates exist; the old corpus spent 6 |
| OpenSSH | 16 / 20 | ran out of unspent templates |

Quotas were declared as ceilings, so shortfalls are reported rather than
backfilled from template-rich systems.

**OpenStack's shortfall is not 15 missing lines, it is three missing fields.**
`trace_id`, `status_code` and `latency_ms` are non-null only on OpenStack lines.
That system was 18.9% of the old corpus and is 1.9% of this one, so P1 tests
*abstention* on those three fields and cannot test *extraction* of them at all.

---

## Label provenance — the finding

The gold labels are **not hand-written**:

| field | source | n |
|---|---|---|
| `message` | Loghub-2.0 `Content` column | 96 |
| the other six | Claude (Opus 5) applying `ADJUDICATION.md` | 94 records |
| the other six | hand-written by the author | 2 records |

`rule_parser.py` is an implementation of `ADJUDICATION.md`. A model applying that
same document produces labels that agree with the parser wherever the parser
implements its own spec. **Gate A therefore measures spec-conformance, not
generalisation.**

This is finding 2 of the amendment reappearing in a new place. It was written
down before the gate ran.

**No third-party check can offset it.** Loghub-2.0's structured CSV is
`LineId, Content, EventId, EventTemplate` — it annotates no `Level` and no
`Component`. `validate_labels_loghub.py`, which corroborated the previous corpus
at 127/127 on `level`, **cannot run on P1 at all**.

---

## Gate A

```
python3 real-eval/score_arms.py --labels real-eval/labels_p1.jsonl rules
```

| arm | exact (7) | six-field | n |
|---|---|---|---|
| rules | **100.0%** | **100.0%** | 96 |

All seven fields, 96/96, zero hallucinations. **This number is uninformative by
construction** and is reported only because the pre-registration required it to
be reported whichever way it fell.

The comparison is the point:

| gold | rules six-field |
|---|---|
| old hand-labelled corpus (n=127) | 92.1% |
| this model-labelled corpus (n=96) | 100.0% |

The parser did not improve. The gold moved toward the parser.

---

## The independent labelling — Gate A

All 96 gold records were re-labelled by the author from the raw lines alone, in
two sittings (25, then the remaining 71). The gold was never loaded or displayed.

**Parser vs independent labels:**

| | six-field | note |
|---|---|---|
| as labelled | 72.9% | n=96 |
| correcting the HDFS sub-second error | 83.3% | 10 lines |
| correcting the trace-id transposition | **84.4%** | 1 line — **the reported figure**, 95% CI [77.1, 90.6] |
| additionally excluding Zookeeper `service` | 97.9% | 13 lines — **not applied** |

**Per field, at the reported adjudication:**

| field | agreement |
|---|---|
| `level` | **100.0%** (96/96) |
| `status_code`, `latency_ms` | 100.0% |
| `trace_id` | 97.9% |
| `timestamp` | 100.0% after correction (89.6% raw) |
| `service` | 85.4% |

### The two corrections, and why they are factual

**HDFS sub-seconds came from the PID column.** All ten HDFS timestamp
disagreements have the author writing sub-seconds that are the leading digits of
the PID:

```
081111 070640 20570 INFO dfs.DataNode$BlockReceiver: …
       └time┘ └PID┘        author wrote .205
081109 234826  4185 INFO …  author wrote .418
081110 104936    16 WARN …  author wrote .016
```

10 of 10. HDFS's format is `yymmdd hhmmss pid LEVEL component:` and has no
sub-second field, so these digits provably come from a different column.

**The trace id is a transposition.** The line reads `…-46b0-…`; the author wrote
`…-4b60-…`.

### The Zookeeper divergence — left standing

13 of the 14 remaining `service` disagreements are Zookeeper lines labelled null
where S1b takes the class immediately before `@<num>`: `Follower`, `Environment`,
`SessionTrackerImpl`, `FastLeaderElection`, `CommitProcessor`, `Leader`,
`FileTxnLog`, `QuorumPeer`.

The behaviour is consistent across both passes, and the same annotator filled
`service` for Linux, HDFS, Spark, Hadoop and HealthApp — so it reads as a
position, not fatigue. In
`[QuorumPeer[myid=1]/0:0:0:0:0:0:0:0:2181:Follower@118]`, `Follower` is a class
name inside a thread descriptor, and calling it *the service* is a real stretch.

S1b was itself added under pressure from the previous corpus. A second reader did
not reproduce it. That is recorded as an open question about the rule rather than
settled in the parser's favour, and the 13 lines are **not** excluded from the
score. If they are later confirmed as uncertainty rather than judgment, the
figure moves to 97.9%.

---

## Verdict

Gate A's declared branches: *rules holds near 92% → proceed*; *rules falls to
75–80% → the published figure was fitting, stop and correct the README*.

**The falsification branch fires.** 84.4%, 95% CI [77.1, 90.6], **excludes
92.1%** and contains the 75–80% band. The published figure does not survive labels
that did not come from the parser's own rulebook.

**What survives:** `level` at 96/96 against an independent annotator, covering
every gold-null line across Linux, OpenSSH, HealthApp and Proxifier. The
abstention behaviour — knowing when *not* to emit a field — is the part of this
project that holds up on an independent corpus.

**What does not:** the extraction accuracy headline. 92.1% is an artefact of a
corpus co-developed with the parser, and is reported as such.

---

## Final: three arms on the P1 corpus

96 lines, scored against labels the author wrote blind from the raw lines, with
the two provable annotation errors corrected (`spotcheck_p1_adjudicated.jsonl`).
These labels are independent of the parser's rulebook, of the training data, and
of every arm.

| arm | six-field | 95% CI | unparseable |
|---|---|---|---|
| **rules** (`rule_parser.py`) | **84.4%** | 77.1 – 90.6% | 0 |
| gemini-3.1-pro-preview | 78.1% | 69.8 – 86.5% | 0 |
| Qwen3-4B fine-tune (v2) | 60.4% | 50.0 – 70.8% | 1 |

**McNemar's exact test, paired, on six-field match:**

| comparison | discordant | p | result |
|---|---|---|---|
| rules vs gemini | 6 – 0 | 0.031 | rules |
| rules vs fine-tune | 23 – 0 | < 0.0001 | rules |
| gemini vs fine-tune | 20 – 3 | 0.0005 | gemini |

The ordering is strict and every pair separates. Rules lost no discordant pair to
either arm.

### Per field

| field | rules | gemini | fine-tune |
|---|---|---|---|
| timestamp | 100.0% | 100.0% | 99.0% |
| level | **100.0%** | 97.9% | 99.0% |
| service | 85.4% | 83.3% | 70.8% |
| trace_id | 99.0% | 99.0% | 97.9% |
| status_code | 100.0% | 99.0% | 96.9% |
| latency_ms | 100.0% | 97.9% | 90.6% |

`message` reads 0.0% for all three: the blind pass collected only the six
judgement fields, so there is no gold `message` to score against. Six-field is
the figure throughout.

### Abstention — non-null emitted where the gold is null

| field | rules | gemini | fine-tune |
|---|---|---|---|
| **level** | **0 / 32** | 2 / 32 | **0 / 32** |
| status_code | 0 / 96 | 1 / 96 | 2 / 96 |
| latency_ms | 0 / 96 | 2 / 96 | 8 / 96 |
| service | 13 / 24 | 15 / 24 | 14 / 24 |

**The v2 abstention result survives an independent corpus.** On `level` the 4B
fine-tune matched the deterministic parser at 0/32 and beat the frontier model,
on log formats it has never seen, against labels written blind. That was the
prediction v2 was built to test, and it holds.

Its extraction does not: `service` at 70.8% and `latency_ms` with 8 invented
values are why it finishes 24 points behind the parser. *Abstention is learnable
per-field from nulls in the training distribution; extraction is not* — the v2
conclusion, now confirmed on data from a different generative process.

`service` hallucination is high for all three because the annotator labelled
Zookeeper `service` null on 13 lines where S1b takes the class before `@<num>`.
Every arm follows S1b. That column measures the disputed rule, not the arms.

### The fine-tune's failure taxonomy, and the P0 prediction

`v3/PREREGISTRATION.md`, written before this corpus existed, diagnosed v2's
errors as concentrating in two families: Hadoop nesting a logger class inside a
thread bracket, and durations in prose read as latency. On P1, the fine-tune's
23 field errors break down as:

| failure | n |
|---|---|
| `service` = the thread token, or the dotted logger shortened to its last segment (S1) | 12 |
| `latency_ms` invented from a duration in the message text (F5 / P1) | 8 |
| `status_code` invented (P1) | 2 |
| unparseable JSON | 1 |

Same two families, same rank order, on a corpus from a different Loghub release
with zero template overlap. The diagnosis in the original pre-registration was
correct and is stable across corpora.

```
gold  org.apache.hadoop.ipc.Server       pred  "Socket Reader #1 for port 32070"
gold  org.apache.hadoop.mapred.MapTask   pred  "main"
gold  org.apache.hadoop.ipc.Client       pred  "communication thread"
```

One of the two `status_code` errors is a pure hallucination rather than a
misplacement: on `[error] [client ...] Invalid URI in request GET  HTTP/1.1` the
model emitted `status_code: 400`. No `400` appears anywhere in that line — it was
inferred from the semantics of an invalid request. That is the abstention failure
this schema exists to measure, caught in the act.

### On the published comparison

This does **not** cleanly overturn the `p = 0.27` indistinguishability reported
on the previous corpus. That was 127 lines with 24 OpenStack records; this is 96
lines with 2. The compositions differ too much for a direct read-across. The
defensible claim is the standalone one: **on this corpus, against these labels, a
250-line deterministic parser beats gemini-3.1-pro-preview, p = 0.031.**

## Incidental findings

**Finding 4 of the amendment is confirmed, with one correction.** Header recovery
is 100.0% on all 14 systems; line counts match to the digit (Linux 23,921,
Apache 51,978, Proxifier 21,320, Mac 100,314 / 626 templates, HPC 429,988); the
in-distribution total is 28,653,315 — the amendment's "28.7M". T1 trap candidates
recompute to **4,442**, exactly the figure claimed.

Recovery must be measured under collapsed whitespace: Loghub-2.0 normalises runs
of spaces inside `Content`, so a literal comparison reads 81.6% on Linux where
the true figure is 100.0%.

**One trap count does not reconcile, and it changes a design decision.**
`L3_severity_in_prose` measures **3,224** across the ten in-distribution systems,
against the amendment's 441,478 — a density of 0.011%. Reaching 441,478 from
1.94M lines needs 22.8%, and no Loghub-2.0 system approaches it; the highest are
HPC 14.2%, Thunderbird 12.8%, Mac 12.1%, all **out-of-distribution systems v3 may
not train on**. The claim that severity traps are abundant enough to mine rather
than generate is **not supported for `level` on in-distribution data**.

**Four in-distribution lines could not be labelled** and are in
`ambiguous_p1.jsonl` rather than guessed: three HealthApp lines whose date is
`201812` — six digits where the format is `yyyymmdd` — and one Spark line that is
a Java stack-trace continuation with no timestamp, level or logger position.

---

## Reproducing

```bash
python3 v3/fetch_loghub1.py                        # 1.0 2k annotations
# download Loghub-2.0 per v3/COLAB_P1.md
python3 v3/measure_loghub2.py --data loghub2 --out v3/MEASUREMENTS_P1.txt
python3 v3/build_corpus_p1.py --data loghub2 --out real-eval
python3 real-eval/score_arms.py --labels real-eval/labels_p1.jsonl   rules
python3 real-eval/score_arms.py --labels real-eval/spotcheck_p1.jsonl rules
python3 real-eval/spotcheck_compare.py
```

`message` is null in `spotcheck_p1.jsonl` — the spot-check collected only the six
judgement fields — so the seven-field number there reads 0.0% and should be
ignored. Six-field is the figure.
