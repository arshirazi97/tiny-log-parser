# Test labels — provenance and open decisions

`labels_test.jsonl` is a **machine-proposed** pass over all 127 lines
(`_labelled_by: claude-proposal-v1`, `_review: pending`), written from
`ADJUDICATION.md`. It is not ground truth until reviewed.

## What this costs, stated plainly

The labels were produced by the same author as `rule_parser.py`. Measured:

> **My labels and my parser agree on 127/127 lines.** The only three
> differences are float representation (`267.2651` vs `267.26509999999996`),
> which the scorer treats as equal at 1e-9 tolerance.

So the **rules arm will score 100% on this test set by construction.** That
number is not evidence of anything and must not be reported as accuracy.

What this does *not* invalidate:

- **The Gemini arm.** Fully independent of both the labels and the training
  data. This is the real comparison.
- **The fine-tune arm**, with a caveat: its training data came from the same
  author applying the same rules, so shared assumptions inflate it somewhat.
  It scored 74% six-field on dev rather than 100%, so it is clearly not
  reproducing the labels mechanically — but the number should be read as an
  upper bound.

To recover the rules arm as a real comparison, the labels have to come from
someone else, or you have to review and change enough of them that agreement
with the parser stops being total.

## Distribution

| field | null |
|---|---|
| timestamp | 0/127 |
| level | 53/127 |
| service | 9/127 |
| trace_id | 103/127 |
| status_code | 113/127 |
| latency_ms | 113/127 |

`level` null on exactly Linux (15), OpenSSH (14), HealthApp (12) and
Proxifier (12) = 53, the four sources with no level position. `service` null on
exactly the 9 Apache lines (S3). `trace_id` non-null on exactly the 24
OpenStack lines. Consistent with the rules; worth spot-checking a few yourself.

## Open decisions — 10 flagged rows

**`year-recoverable-from-message-text` — 5 rows.** The biggest one.

```
Jun 22 13:16:30 combo ftpd[17886]: connection from 210.245.165.136 () at Wed Jun 22 13:16:30 2005
```

Rule T1 says the 1900 sentinel applies because "the year is not recoverable from
the line". Here it **is** recoverable — `2005` sits in the message text. Five
ftpd lines do this.

- **Proposed:** `1900-06-22T13:16:30Z`. T1 is about the *timestamp field*, and
  reading the year out of prose is a different operation.
- **Alternative:** `2005-06-22T13:16:30Z`. Truer to "recoverable", but requires
  every system to parse an English date out of free text.
- Either way T1 needs rewording, because as written it is ambiguous here.

**`syslogd-version-in-tag` — 1 row.** `combo syslogd 1.4.1: restart.`
Proposed service `syslogd 1.4.1`. Alternative: `syslogd`, treating `1.4.1` as a
version rather than part of the name. S2 covers `(pam)` and `[pid]` but not this.

**`proxy-status-code-in-prose` — 1 row.** A Proxifier error ending
`... status code 403`. Proposed `status_code: null` — it is prose in a proxy
error, not a structural status field. Alternative: `403`.

**`openstack-took-N-seconds-in-prose` — 1 row.**
`Took 0.45 seconds to deallocate network for instance.` Proposed
`latency_ms: null`. Unlike F5's timeout and lifetime cases this *is* a measured
duration of the logged operation, so `450.0` is arguable. It sits in prose, not
in a `time:` field.

**`zk-timeout-null-per-F5` — 2 rows.** Not open; F5 already decides these.
Flagged only so you can see F5 being applied.

## Sign-off

Review, correct anything you disagree with, then flip `_review` to
`human-approved`. `score_arms.py` stamps every run PROVISIONAL until you do.
