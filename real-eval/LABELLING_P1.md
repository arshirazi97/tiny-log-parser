# Labelling the P1 corpus — per-system quick reference

Companion to `ADJUDICATION.md`, which remains the authority. Every example here
is taken from `ADJUDICATION.md` itself or from the Loghub 1.0 2k samples, never
from `corpus_p1.jsonl` — so no line you are about to label has been pre-decided.

**162 in-distribution lines across ten systems.** The 100 OOD lines (BGL,
Thunderbird, Mac, HPC) have unresolved rule gaps: flag them `!ood` and skip.

Constant across almost every line: `trace_id`, `status_code`, `latency_ms` are
**Enter** (null). Only OpenStack carries them. That is F1, and inventing a value
there is a hallucination, not a near-miss.

---

## Timestamp, in one line per system

| system | raw form | label |
|---|---|---|
| Zookeeper, Hadoop | `2015-07-30 17:52:38,191` | `2015-07-30T17:52:38.191Z` |
| HDFS | `081109 203615` | `2008-11-09T20:36:15Z` |
| Spark | `17/06/09 20:10:40` | `2017-06-09T20:10:40Z` |
| OpenStack | `2017-05-16 00:00:00.008` | `2017-05-16T00:00:00.008Z` |
| HealthApp | `20171223-22:15:29:606` | `2017-12-23T22:15:29.606Z` |
| Apache | `[Sun Dec 04 04:47:44 2005]` | `2005-12-04T04:47:44Z` |
| Linux | `Jun 14 15:16:01` | `1900-06-14T15:16:01Z` |
| OpenSSH | `Dec 10 06:55:46` | `1900-12-10T06:55:46Z` |
| Proxifier | `[07.26 14:51:37]` | `1900-07-26T14:51:37Z` |

Bottom three have no year in the line: T1 sentinel `1900`. Everything gets `Z`
(T2). Sub-seconds are preserved exactly, never padded or truncated (T3).

---

## Level

| system | source | label |
|---|---|---|
| HDFS, Spark, Zookeeper, Hadoop, OpenStack | token in its own position | as written, `WARN`→`WARNING` |
| Apache | `[notice]` | `INFO` (L2) |
| Linux, OpenSSH, HealthApp, Proxifier | **none** | **null** |

The four null systems are the abstention test. `authentication failure`,
`error :`, `Error -60005` are prose, not levels — L1 and L3. This is the single
most important thing in the set to get right.

---

## Service

| system | rule | example |
|---|---|---|
| HDFS, Spark, Hadoop | S1 — full dotted logger, as written | `dfs.DataNode$PacketResponder` |
| Zookeeper | S1b — class before `@<line>`, **not** the thread | `[SessionTracker:ZooKeeperServer@325]` → `ZooKeeperServer` |
| OpenStack | S4 — the logger after the PID, not the filename | `nova.osapi_compute.wsgi.server` |
| Linux, OpenSSH | S2 — process, drop `(pam_unix)` and `[pid]` | `sshd(pam_unix)[19939]` → `sshd` |
| Linux | S2b — a **version suffix stays** | `syslogd 1.4.1: restart.` → `syslogd 1.4.1` |
| Proxifier | S2c — an **architecture marker stays** | `chrome.exe *64 - ...` → `chrome.exe *64` |
| HealthApp | the component field | `20171223-...\|Step_LSC\|300...` → `Step_LSC` |
| Apache | S3 — **null** | never `apache`, `httpd`, or `unknown` |

---

## The three rare fields — OpenStack only

Five lines in this corpus. Everywhere else: Enter, Enter, Enter.

```
nova-api.log.1.2017-05-16_13:53:08 2017-05-16 00:00:00.008 25746 INFO
nova.osapi_compute.wsgi.server [req-38101a0b-2096-447d-96ea-a692162415ae ...]
... status: 200 len: 1893 time: 0.2598419
```

- `trace_id` → `req-38101a0b-2096-447d-96ea-a692162415ae`, keeping `req-` (F2)
- `status_code` → `200`
- `latency_ms` → `259.8419` — seconds × 1000, **not rounded** (F4)
- `message` → everything after the `[req-…]` bracket, **verbatim**, including
  `status:` and `time:` (M1b)

Two traps that stay null anywhere else:

- HDFS `blk_-6952295868487656571` is a block id, not a trace id (F3)
- Zookeeper `timeout of 10000ms exceeded` and Proxifier `lifetime <1 sec` are a
  configured timeout and a connection lifetime, not the duration of the logged
  operation (F5)

---

## Message

The remainder after the fields are taken out, structural punctuation and
trailing whitespace stripped, everything else kept verbatim — IPs, paths, ids
all stay (M1). Scored separately from the other six (M2), so a formatting
quibble does not swamp the extraction result.

---

## At the prompt

```
?        the schema and rules
<        back up one field
!<note>  flag and skip -- use !ood for OOD lines
q        save and quit (resumable; just re-run)
```

Flag rather than guess. `ADJUDICATION.md` says so explicitly, and a flagged line
resolved in a batch against a written rule is defensible where a guess made at
2am is not.
