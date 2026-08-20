# Adjudication rules — real-log test set

These rules were written from the raw corpus before labelling and before either
system was run. They ship with the test set. Both the fine-tune and the baseline
receive the same schema spec including these rules.

Every rule here exists because a real corpus contains something the synthetic
generator never produced. That gap is the point of the exercise.

---

## Timestamp

**T1 — no year in the line.** Syslog-derived sources (Linux, OpenSSH) and
Proxifier emit `Jun 14 15:16:01` or `[10.30 16:49:06]` with no year. The year is
not recoverable from the line.
→ Emit the year as `1900`. A fixed sentinel is scoreable; a guessed year is not.
Both systems are told this rule.

**T2 — no timezone in the line.** Almost no real source states an offset.
→ Assume UTC and emit `Z`. Where an offset *is* present, normalise to UTC.

**T3 — sub-second precision.** Preserve what the line gives (`,747` → `.747`,
`:606` → `.606`). Do not pad or truncate.

**T4 — compact date forms.** HDFS `081109 203615` is `yymmdd hhmmss`; Spark
`17/06/09` is `yy/mm/dd`. Two-digit years resolve to 20xx.

## Level

**L1 — absent means null.** Linux, OpenSSH, HealthApp and Proxifier lines carry
no level token. Do **not** infer a level from the wording of the message
("authentication failure" is not ERROR). Absent → `null`.
This is the single most important abstention test in the set.

**L2 — canonical vocabulary.** `TRACE DEBUG INFO WARNING ERROR FATAL`.
Map `WARN`→`WARNING`, `notice`→`INFO`, `err`→`ERROR`, `crit`/`critical`→`FATAL`.

**L1b — an HTTP status code does not imply a level.** An access-style line
carrying `status: 200` or `" 503 ` but no level token has level `null`. The
status belongs in `status_code`; inferring ERROR/WARNING/INFO from it is the
same context-inference L1 forbids. (This reverses the v1 spec, which mapped
5xx->ERROR. Both arms are scored against the rule as written here.)

**L3 — severity in the message body.** If a level-like word appears only inside
the human-readable text and not in a structural level position, it is not a
level. → `null`.

## Service

**S1 — logger class.** Hadoop/Spark/Zookeeper/HDFS emit a fully-qualified
logger (`org.apache.hadoop.mapreduce.v2.app.MRAppMaster`,
`dfs.DataNode$PacketResponder`). Take the **full string as written**, before the
first `:` separator. Do not shorten to the last segment.

**S2 — syslog process.** `sshd(pam_unix)[19939]` → service is `sshd`. Drop the
PAM qualifier and the PID.

**S3 — no service present.** Apache `[notice] workerEnv.init() ok` has no
service position. → `null`. Do **not** emit `apache`, `httpd`, `unknown`, or any
placeholder. Inventing a value here counts as a hallucination, not a near-miss.

**S4 — OpenStack.** The line begins with a log *filename*
(`nova-api.log.1.2017-05-16_13:53:08`), not a service. The service is the
logger that follows the PID: `nova.osapi_compute.wsgi.server`.

## trace_id / status_code / latency_ms

**F1 — absent means null, always.** These three fields do not exist outside
HTTP-ish service logs. In the sparse stratum they are null on nearly every line.
Any non-null value where the line contains no such field is a hallucination.

**F2 — OpenStack trace.** `[req-38101a0b-2096-447d-96ea-a692162415ae ...]` →
trace_id is `req-38101a0b-2096-447d-96ea-a692162415ae`, including the `req-`
prefix.

**F3 — HDFS block ids are not trace ids.** `blk_-6952295868487656571` is a data
identifier, not a request correlation id. → `null`.

**F4 — OpenStack latency.** `time: 0.2477829` is seconds → `247.7829` ms.
Do not round.

## Message

**M1 — remainder after field extraction**, with structural punctuation and the
trailing whitespace stripped. Embedded IPs, paths and ids stay in the message.

**M2 — the message is scored last and separately.** It is the most
judgement-dependent field; report exact-match on it but also report the
six-field exact-match excluding it, so a formatting quibble does not swamp the
extraction result.

---

## Flagging

If a line does not fall cleanly under a rule above, flag it with `!note` in
`label.py` rather than guessing. Resolve flagged lines in a batch, write the new
rule here, then re-run the labeller. A test set whose ambiguities were resolved
ad hoc during labelling is not defensible; one that ships its rule list is.
