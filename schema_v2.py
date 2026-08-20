"""Schema v2 -- the spec both systems receive for the real-log evaluation.

v1 (eval.py SPEC) had no way to say "this field is not present". Every one of
its 20,000 training examples carried a level and a service, and the dev-corpus
probe showed the consequence: the model emitted a non-null level on 50/50 real
lines, including 16 that contain no level token at all -- while abstaining
correctly on trace_id (82% null), status_code (90%) and latency_ms (82%), the
three fields that DID have nulls in training.

Abstention is learned per-field from nulls in the data. v2 adds them.

Rules mirror real-eval/ADJUDICATION.md so the same spec scores both the
synthetic set and the real corpus.
"""

FIELDS = ["timestamp", "level", "service", "trace_id",
          "status_code", "latency_ms", "message"]

LEVELS = ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "FATAL"]

SPEC = """Normalize the log line into JSON with exactly these keys:

  timestamp   ISO8601 UTC with a "Z" suffix. Convert from any offset.
              Preserve sub-second digits exactly as the line gives them
              ("...,747" -> ".747Z", "...:606" -> ".606Z"). Do not pad,
              truncate or invent them; if the line has none, emit none.
              If the line has no year, use 1900 as the year.
              Two-digit years resolve to 20xx ("081110" -> 2008-11-10,
              "17/06/09" -> 2017-06-09). Epoch seconds/millis allowed.
  level       One of: TRACE DEBUG INFO WARNING ERROR FATAL.
              Map aliases: DBG->DEBUG, NOTICE->INFO, WARN/W->WARNING,
              ERR/E->ERROR, CRIT/CRITICAL/FATAL->FATAL.
              Syslog numeric severities: 2->FATAL, 3->ERROR, 4->WARNING,
              5/6->INFO, 7->DEBUG.
              If the line carries no level token, emit null -- including when
              an HTTP status code is present. Do NOT infer a level from the
              status code, and do NOT infer one from the wording of the
              message; "authentication failure" is not ERROR. A level-like
              word inside the human-readable text is not a level.
  service     The emitting component, as written. Keep dotted or nested
              logger paths whole ("dfs.DataNode$PacketResponder", not
              "PacketResponder"). Drop a trailing [pid] and any parenthesised
              qualifier. If the line has no service position, emit null --
              never invent "unknown", "app" or any other placeholder.
  trace_id    A request-correlation id: 32-char lowercase hex, or a "req-"
              prefixed UUID (keep the "req-" prefix). null if absent.
              Block ids, job ids, session ids, thread ids and PIDs are NOT
              trace ids. Never invent one.
  status_code Integer HTTP status, or null if not an HTTP event.
  latency_ms  Milliseconds. Convert units: "0.234s"->234, "234000us"->234,
              "rt=1.500"->1500, "time: 0.2477829"->247.7829.
              Do not round. null if absent.
  message     The human-readable message only. For access logs use
              "METHOD /path". Collapse whitespace. No trailing metadata.

Output only the JSON object. No markdown fences, no commentary."""


def canon_ts(dt, frac=None, year_known=True):
    """Canonical timestamp string. year_known=False emits the 1900 sentinel."""
    y = dt.year if year_known else 1900
    s = (f"{y:04d}-{dt.month:02d}-{dt.day:02d}"
         f"T{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}")
    return s + (f".{frac}Z" if frac else "Z")
