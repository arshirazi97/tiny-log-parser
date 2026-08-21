# Dev labels — open decisions for review

`labels_dev.jsonl` is a **machine-proposed first pass** (`_labelled_by:
claude-proposal-v1`, `_review: pending`). It was written from `ADJUDICATION.md`,
not from any system's output.

**It is not ground truth until a human signs off.** Two reasons this matters:

1. An LLM writing the gold for an evaluation whose arms include two LLMs is the
   "means essentially nothing" objection in a new form.
2. The same author wrote `rule_parser.py`, so these labels carry that parser's
   assumptions. That arm would partly grade itself.

Dev is only used to iterate, and is never reported as a result — which is why a
proposed pass is acceptable here. **The 127-line test set must be hand-labelled**,
and the writeup should say so plainly.

19 of 50 rows carry a flag. Each is a real ambiguity in the rules, not a
transcription doubt. Resolve them, write the answer into `ADJUDICATION.md`, then
re-run the labeller or patch the file.

---

## 1. `zk-service` — 6 dev rows, ~9 test rows

```
2015-08-20 17:14:24,000 - INFO  [SessionTracker:ZooKeeperServer@325] - Expiring session ...
```

Rule S1 says "take the full string as written, before the first `:` separator."
Applied literally that gives **`SessionTracker`** — which is the *thread*, not
the logger. The logger is **`ZooKeeperServer`**.

- **Proposed:** the class before `@` → `ZooKeeperServer`, `PrepRequestProcessor`,
  `NIOServerCnxn`, `FastLeaderElection`.
- **Alternative:** the literal S1 reading → `SessionTracker`, `ProcessThread(sid:2 cport:-1)`.
- Whichever you pick, S1 needs rewording — it does not currently cover a logger
  nested inside a thread bracket.

## 2. `openstack-message` — 5 dev rows, ~24 test rows (the biggest one)

```
... [req-... - - -] 10.11.10.1 "GET /v2/.../servers/detail HTTP/1.1" status: 200 len: 1893 time: 0.2598419
```

`status: 200` and `time: 0.2598419` are extracted into `status_code` and
`latency_ms`. Rule M1 says message is "the remainder **after field extraction**",
which implies they should come *out* of the message.

- **Proposed:** keep the remainder verbatim, including `status:` and `time:`.
  Reproducible and unambiguous to score.
- **Alternative:** strip them → `10.11.10.1 "GET /v2/... HTTP/1.1" len: 1893`.
- ~19% of the test set rides on this. Decide before unfreezing.

## 3. `proxifier-lifetime` — 3 dev rows, ~12 test rows

```
[10.30 16:49:10] chrome.exe - proxy...:5070 close, 1093 bytes sent, ..., lifetime 00:01
```

A connection *lifetime* is a duration, but is it this schema's `latency_ms`?

- **Proposed:** `null`. Rule F1 says these fields "do not exist outside HTTP-ish
  service logs", and a session lifetime is not a request latency.
- **Alternative:** parse it → `60000`. Note `lifetime <1 sec` (row 29) has no
  exact value, so this alternative needs its own sub-rule.

## 4. `zk-timeout-not-latency` — 2 dev rows

`Expiring session 0x24f3..., timeout of 10000ms exceeded`. Proposed `null`: 10000ms
is a *configured* timeout, not a measured latency. Low risk, but worth stating.

## 5. `inline-warning-prefix` — 1 dev row

```
Jul 25 23:23:13 combo xinetd[26482]: warning: can't get client address: ...
```

`warning:` is the first token of the application text, not a syslog level field.

- **Proposed:** `null`, per rule L3 (a level-like word not in a structural level
  position is not a level).
- **Alternative:** `WARNING`. This one is genuinely arguable — it reads as a
  severity prefix — and it is a good probe of how strictly L3 is meant.

## 6. Smaller ones — 1 row each

| flag | line | proposed |
|---|---|---|
| `trailing-colon` | HDFS `... to /10.251.122.79:` | keep the trailing `:` (truncated source line) |
| `double-space-collapsed` | Hadoop `exception  for block` | collapse to one space |
| `apache-client-bracket` | `[error] [client 141.153.150.164] Directory index...` | keep `[client ...]` in the message |
| `proxifier-star64` | `chrome.exe *64 - ...` | service is `chrome.exe`, `*64` dropped |
| `pam-prefix-in-message` | `sshd[24224]: pam_unix(sshd:auth): authentication failure; ...` | service `sshd`; `pam_unix(...)` stays in the message |

---

## Proposed label distribution

| field | null |
|---|---|
| timestamp | 0/50 |
| level | **17/50** |
| service | 3/50 |
| trace_id | 44/50 |
| status_code | 45/50 |
| latency_ms | 45/50 |
| message | 0/50 |

`level` at 17/50 lines up with the independent detector count (16/50) used by the
abstention probe, which is a mild consistency check on both.

## Sign-off

After reviewing, flip `_review` to `human-approved` (and correct any labels you
disagree with). Until then, treat every dev number computed from this file as
provisional.
