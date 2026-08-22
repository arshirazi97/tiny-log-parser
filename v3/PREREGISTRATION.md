# v3 — pre-registration

Written **before** the training set exists and before any v3 model is trained.
Committed ahead of the run so the predictions cannot be adjusted to fit the
result. This is the same discipline that made the v2 abstention result worth
reporting: it was predicted at 70–90%, came back at 34%, and the miss was
reported.

## Hypothesis

v2's remaining failures are **training-distribution gaps, not capability
limits**. It was trained on 11 invented format renderers and tested on ten real
systems, so it never saw the conventions it fails on. Training on real logs
should eliminate them.

Evidence this is the right diagnosis: 35 of v2's 42 field errors on the test
set are `service` (25) and `latency_ms` (10), and both concentrate in two
families — Hadoop nesting a logger class inside a thread bracket, and
Proxifier's `lifetime` read as a latency. Neither pattern exists in any
synthetic renderer.

## Predictions

Scored on a **fresh** corpus, never touched during v3 development:

| quantity | v2 (measured) | v3 prediction |
|---|---|---|
| `service` field errors | 25 / 127 | **< 8** |
| `latency_ms` field errors | 10 / 127 | **< 4** |
| six-field exact, in-distribution | 73.2% | **> 88%** |
| `level` hallucination on gold-null | 1 / 53 | **≤ 2 / 53** (must not regress) |

**Falsification.** If `service` errors stay above 15, the hypothesis is wrong:
the gap is not explained by training distribution and a larger model or a
different approach is indicated. That outcome gets reported, not buried.

**Not a success criterion:** beating gemini-3.1-pro. The experiment tests a
mechanism. Beating the baseline is a possible outcome, not the goal — setting it
as the goal is what produced the v1 result Andy correctly rejected.

## Design

**Two evaluation sets, reported separately.**

- **In-distribution** — the ten systems v3 trains on, but lines and whole
  template families held out from training. This is the realistic deployment:
  a model fine-tuned on the log formats it will actually see.
- **Out-of-distribution** — systems v3 has never seen (BGL, Thunderbird,
  Windows, Mac, Android, HPC). This is what v2 measured, and where the fine-tune
  is expected to remain behind.

The interesting claim is the contrast, not either number alone.

**Contamination control.** No line in either eval corpus, and no line sharing a
template signature with one, may enter training. Enforced in code, verified by
an explicit check before training.

## Where the training labels come from

Not from `rule_parser.py` — training on the parser's output would distil the
parser and re-couple the labels to their author.

| field | source |
|---|---|
| `level` | Loghub `Level` column, alias-normalised. Absent column → null |
| `service` | Loghub `Component` column, per-source normalisation |
| `message` | Loghub `Content` column |
| `timestamp` | deterministic assembly from Loghub's Date/Time columns |
| `trace_id`, `status_code`, `latency_ms` | focused per-source extraction; null by default |

Three of seven fields come from third-party annotations. `timestamp` is
mechanical. The last three are ours, and that coupling is disclosed rather than
claimed away.

**Known exception:** for OpenSSH, Loghub's `Component` column holds the hostname
(`LabSZ`), not the daemon. Rule S2 governs and the daemon is extracted from the
raw line. This is the one place the training labels deliberately depart from
Loghub's annotations, and it is the same disagreement documented in
`ADJUDICATION.md`.

## Budget

~$0.75 GPU (RunPod, ~2.5h), ~$4 baseline API on the fresh corpus, ~$5 total.
