# V4 — pre-registration

Written **2026-08-24**, before any v4 training data is generated and before any
model is trained. `PREREGISTRATION_P2.md` stands; this supersedes nothing.

The v3 artifacts are pinned in `v3/V3_FREEZE.txt` and the eval inputs in
`real-eval/EVAL_FREEZE_V4.txt`. Both must verify before and after this work.
v4 writes only new files — `generate_v4.py`, `build_train_v4.py`,
`train_v4.jsonl`, and a separate HuggingFace repo. **v3 stays reproducible.**

---

## Why this is not test-set tuning

Every fix below was identified by reading v3's errors on evaluation data. That
is only legitimate under two conditions, and both are met:

1. **The fixes are declared here, before the data exists**, along with the
   acceptance criterion. Nothing below may be revised after a number is seen.
2. **v4 is scored on corpora it was not diagnosed from.** The six observed
   errors came from `corpus_heldout50.jsonl` and `corpus_demo10.jsonl`. Those
   60 lines are a *regression check*, not the result. The result comes from the
   frozen 500 and from `corpus_v4holdout20.jsonl` — 20 fresh lines, 0/20
   template overlap with training, built before this document and never
   inspected.

## What v3 got wrong

Six field errors across the 60 clean held-out lines, adjudicated against
`ADJUDICATION.md`:

| n | error | cause, measured |
|---|---|---|
| 3 | Linux ftpd: emitted `2005` from the prose where T1 mandates the `1900` sentinel | **0** ftpd lines in training; the whole trap is 70 lines (0.65%) |
| 2 | `su(pam_unix)` → `pam_unix`, where S2 says `su` | training carries **4** process names with a qualifier — `sshd`, `gdm`, `login`, `passwd`. **`su` is absent.** |
| 1 | Proxifier `[10.30 ...]` → month `03` | **1** Proxifier training example, and it was `[07.26 ...]` |

All three are coverage gaps in regions of the input space training barely
occupies. None is a failure to represent the rule: on `pam_unix(sshd:auth)` —
the same S2 rule, with a process name v3 *has* seen — v3 is correct.

## The hypothesis

**v3's residual errors are training-data coverage gaps, not capability limits.
Adding data in exactly those regions closes them without disturbing anything
else.**

The falsifiable form: if these are capability limits rather than coverage gaps,
v4 will fail the same lines despite direct supervision on the pattern.

## What v4 adds

| # | addition | source | target |
|---|---|---|---|
| 1 | Proxifier | mined, 1,302 available | 1 → ~300 |
| 2 | OpenSSH | mined, 380 available | 99 → ~300 |
| 3 | OpenStack | mined, 1,611 available | 21 → ~300 |
| 4 | Linux ftpd + year-in-prose | mined, 33 + 35 available | 0 → all 68 |
| 5 | `F3a_pam_qualifier` | **synthetic** | ~300 |
| 6 | `F3b_year_in_prose` | **synthetic** | ~200 |

Additions 5 and 6 must be synthetic: the Loghub-1.0 caches contain only `sshd`
and `login` in the `X(qualifier)[pid]` position — no `su` — and only 6 distinct
year-in-prose templates. Mining alone cannot teach either rule.

Every mined line is checked against training AND all seven frozen eval corpora,
at exact and template level, before admission. The builder aborts on any hit.

## What v4 does NOT change

Declared so that a later result cannot be attributed to an undeclared edit:

- **Field priors stay as they are.** `latency_ms` 2.97%, `trace_id` 3.17%,
  `status_code` 1.79% non-null. Raising these is the obvious next move and it is
  deliberately **out of scope**: v3's abstention discipline is its best measured
  property — 0 hallucinations across all 60 clean lines, where Gemini
  hallucinated on P1 — and it is learned from exactly these priors. Trading it
  for breadth is a separate experiment with its own pre-registration.
- **No new log formats.** JSON, logfmt and Apache-combined remain at zero. v4 is
  an in-distribution fix, not a generalisation attempt.
- **`ADJUDICATION.md` is unchanged.** Two disputed calls are on record
  (`RESULTS_P1.md`) and stay unresolved here; resolving them would move both
  arms and confound the comparison.
- **The eval corpora, `rule_parser.py`, `schema_v2.py` and the contamination
  guard are frozen.** `EVAL_FREEZE_V4.txt` verifies this.
- **The base model, LoRA config and decoding stay identical to v3.** Greedy,
  `SPEC_EVAL`, same hyperparameters. The only variable is training data.

## Acceptance criterion — decided now

**v4 ships if and only if:**

1. It **beats v3 on the frozen 500**, McNemar on six-field match, and
2. It shows **no regression on the frozen 60** — v4 must not lose a line v3 got
   right, and
3. `validate_v3.py` passes on `train_v4.jsonl` and contamination measures 0
   against every frozen eval corpus.

**If v4 fails any of these, v3 is what gets submitted.** A negative result here
is a real finding — it would say the residual errors are not coverage-limited —
and it gets written up rather than retried with a different mixture.

**One retrain.** If the first v4 loses, the answer is not a second mixture; that
is hill-climbing on the eval. Any further attempt requires a new
pre-registration stating what changed and why.

## What would falsify the hypothesis

- v4 still emits `pam_unix` for `su(pam_unix)` after ~300 targeted examples
- v4 still misreads Proxifier `MM.DD` after ~300 examples
- v4 closes the six known errors but loses others on the frozen 500 — coverage
  bought at the cost of something not being measured here

## Expected effect, stated before the run

v3 scored 54/60 on the clean lines, Gemini 58/60, `rule_parser.py` 60/60. If all
six errors close and nothing regresses, v4 reaches 60/60 on that set — but that
set is the one the diagnosis came from, so **it is not evidence**. The frozen
500 and the fresh 20 are.

The honest prediction: the two syslog families (5 additions, 5 of 6 errors) are
well-posed and should close. Proxifier is one example against a format with a
distinctive `MM.DD` order, and ~300 lines should be sufficient, but it is the
least certain of the three.
