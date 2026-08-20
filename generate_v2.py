"""Synthetic dataset generator, v2 -- adds abstention.

Same strategy as v1: build the CANONICAL record first, then render it into a
messy log line, so the label exists before the input and is correct by
construction. Two things change.

1. FIELDS CAN BE ABSENT. v1 always emitted a level and a service. The dev-corpus
   probe showed the model therefore never emitted null for either on real logs
   (0/50), while abstaining correctly on the three fields that did have nulls in
   v1 (trace_id 82%, status_code 90%, latency_ms 82%). Some renderers here carry
   no level token and some carry no service position, so those two fields now
   have nulls to learn from.

2. DISTRACTOR IDENTIFIERS. Block ids, job ids, session ids and PIDs appear in
   lines whose trace_id is null, so "long identifier-shaped token" stops being
   a cue for trace_id.

DELIBERATELY NOT DONE: no renderer here imitates a Loghub layout. The point is
to teach the schema behaviours -- abstain, keep sub-second digits, sentinel the
missing year, keep logger paths whole -- not to memorise the evaluation corpus.
Design was informed by real-eval/corpus_dev.jsonl only; the test corpus has
never been opened.

    python generate_v2.py --train 20000 --test 200
"""

import argparse
import json
import random
from datetime import datetime, timedelta, timezone

from schema_v2 import FIELDS, LEVELS, canon_ts

LEVEL_ALIASES = {
    "TRACE":   ["TRACE", "trace", "T"],
    "DEBUG":   ["DEBUG", "debug", "DBG", "D", "7"],
    "INFO":    ["INFO", "info", "I", "NOTICE", "notice", "6", "5"],
    "WARNING": ["WARNING", "WARN", "warning", "warn", "W", "4"],
    "ERROR":   ["ERROR", "ERR", "error", "E", "3"],
    "FATAL":   ["FATAL", "CRIT", "CRITICAL", "critical", "fatal", "C", "2"],
}
SYSLOG_SEV = {"FATAL": 2, "ERROR": 3, "WARNING": 4, "INFO": 6, "DEBUG": 7, "TRACE": 7}

SERVICES = [
    "auth-api", "payments", "checkout", "user-profile", "search-indexer",
    "notification-worker", "image-resizer", "session-store", "billing",
    "webhook-dispatcher", "recommendation", "inventory", "cdn-edge",
]
# Nested logger paths -- must be kept whole (spec: service).
LOGGERS = [
    "core.transport.ChannelHandler", "io.pipeline$FlushWorker",
    "svc.ledger.PostingEngine", "net.relay.SocketReader",
    "queue.dispatch.RetryScheduler", "store.index.SegmentMerger",
    "auth.token.RefreshDaemon", "media.encode.FrameWriter",
]
PROCS = ["cronsvc", "authd", "relayd", "indexerd", "cachesvc", "netmond"]
COMPONENTS = ["Stat_Collector", "Batch_Runner", "Sync_Agent", "Probe_Unit"]

TRACE_KEYS = ["trace_id", "traceID", "trace-id", "tid", "X-Trace-Id", "traceId"]

MESSAGES = [
    "connection pool exhausted, waiting for free slot",
    "upstream timed out while reading response header",
    "user session refreshed successfully",
    "failed to acquire advisory lock on shard {n}",
    "cache miss for key user:{n}:preferences",
    "retrying request after transient failure (attempt {n})",
    "background job completed without errors",
    "rate limit exceeded for client {n}",
    "database replica lag exceeded threshold",
    "invalid JWT signature presented by client",
    "webhook delivery failed with non-2xx response",
    "index rebuild finished, {n} documents processed",
    "TLS handshake aborted by peer",
    "disk usage crossed warning watermark",
    "payment intent confirmed and captured",
    "message dropped after exceeding max redeliveries",
    # wording that LOOKS like a level but is not one (spec: do not infer)
    "authentication failure for principal {n}",
    "fatal signal handler installed at startup",
    "debug endpoint disabled in this build",
    "error budget for the month is now {n} percent consumed",
]

PATHS = ["/api/v1/users", "/api/v1/orders", "/healthz", "/api/v2/search",
         "/checkout/session", "/webhooks/stripe", "/assets/logo.svg",
         "/api/v1/auth/token"]
METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]


def rand_hex(n):
    return "".join(random.choice("0123456789abcdef") for _ in range(n))


def rand_uuid():
    return "-".join(rand_hex(k) for k in (8, 4, 4, 4, 12))


def distractor():
    """An identifier-shaped token that is NOT a trace id. Never 32 hex chars."""
    return random.choice([
        lambda: f"blk_{random.randint(-2**60, 2**60)}",
        lambda: f"job_{random.randint(10**12, 10**13)}_{random.randint(1000, 9999)}",
        lambda: f"0x{rand_hex(random.choice([13, 15, 16]))}",
        lambda: f"pid={random.randint(100, 99999)}",
        lambda: f"seg-{rand_hex(random.choice([12, 20, 24]))}",
        lambda: f"attempt_{random.randint(10**12, 10**13)}_{random.randint(1, 99):02d}",
    ])()


# --------------------------------------------------------------------------
# Timestamp renderers -> (rendered, sub-second digits or None, year present?)
# --------------------------------------------------------------------------

def ts_iso_offset(dt):
    off = random.choice([-8, -5, 0, 1, 5, 9])
    local = dt + timedelta(hours=off)
    sign = "+" if off >= 0 else "-"
    if random.random() < 0.4:
        f = f"{random.randint(0, 999):03d}"
        return local.strftime(f"%Y-%m-%dT%H:%M:%S.{f}{sign}{abs(off):02d}:00"), f, True
    return local.strftime(f"%Y-%m-%dT%H:%M:%S{sign}{abs(off):02d}:00"), None, True


def ts_syslog(dt):                      # RFC3164: no year at all
    return dt.strftime("%b %e %H:%M:%S"), None, False


def ts_epoch(dt):
    return str(int(dt.timestamp())), None, True


def ts_epoch_ms(dt):
    f = f"{random.randint(0, 999):03d}"
    return f"{int(dt.timestamp())}{f}", f, True


def ts_apache(dt):
    off = random.choice([-8, -5, 0, 2])
    local = dt + timedelta(hours=off)
    sign = "+" if off >= 0 else "-"
    return local.strftime(f"%d/%b/%Y:%H:%M:%S {sign}{abs(off):02d}00"), None, True


def ts_java(dt):
    f = f"{random.randint(0, 999):03d}"
    return dt.strftime("%Y-%m-%d %H:%M:%S,") + f, f, True


def ts_dotted(dt):
    f = f"{random.randint(0, 999):03d}"
    return dt.strftime("%Y-%m-%d %H:%M:%S.") + f, f, True


def ts_compact(dt):                     # yymmdd hhmmss -> two-digit year
    return dt.strftime("%y%m%d %H%M%S"), None, True


def ts_slash(dt):                       # yy/mm/dd
    return dt.strftime("%y/%m/%d %H:%M:%S"), None, True


def ts_pipe(dt):                        # unpadded h:m:s plus millis
    f = f"{random.randint(0, 999):03d}"
    return f"{dt.strftime('%Y%m%d')}-{dt.hour}:{dt.minute}:{dt.second}:{f}", f, True


def ts_md_noyear(dt):                   # "10.30 16:49:10" -- no year
    return dt.strftime("%m.%d %H:%M:%S"), None, False


# --------------------------------------------------------------------------
# Latency -> (rendered, canonical ms)
# --------------------------------------------------------------------------

def fmt_latency():
    style = random.choice(["ms", "s", "us", "plain", "sec7"])
    if style == "sec7":                 # fractional seconds, must not round
        ms = round(random.uniform(1, 8000), 4)
        return f"{ms / 1000:.7f}", ms
    ms = random.randint(1, 8000)
    if style == "ms":
        return f"{ms}ms", ms
    if style == "s":
        return f"{ms / 1000:.3f}s", ms
    if style == "us":
        return f"{ms * 1000}us", ms
    return str(ms), ms


# --------------------------------------------------------------------------
# Line renderers. `caps` says which fields the format can express at all --
# a format with no level position is how the model learns to emit null.
# --------------------------------------------------------------------------

def r_logfmt(r, dt):
    ts, frac, yr = random.choice(
        [ts_iso_offset, ts_iso_offset, ts_epoch])(dt)
    parts = [f"ts={ts}", f"level={random.choice(LEVEL_ALIASES[r['level']])}",
             f"service={r['service']}"]
    if r["trace_id"]:
        parts.append(f"{random.choice(TRACE_KEYS)}={r['trace_id']}")
    elif random.random() < 0.4:
        parts.append(distractor())
    if r["latency_ms"] is not None:
        parts.append(f"duration={r['_lat_txt']}")
    parts.append(f'msg="{r["message"]}"')
    random.shuffle(parts)
    return " ".join(parts), frac, yr


def r_syslog(r, dt):
    ts, frac, yr = ts_syslog(dt)
    pri = 8 * 16 + SYSLOG_SEV[r["level"]]
    host = f"{random.choice(['web', 'app', 'edge'])}-{random.randint(1, 40):02d}"
    tail = r["message"]
    if r["trace_id"]:
        tail += f" [{random.choice(TRACE_KEYS)}={r['trace_id']}]"
    elif random.random() < 0.4:
        tail += f" [{distractor()}]"
    if r["latency_ms"] is not None:
        tail += f" took={r['_lat_txt']}"
    return (f"<{pri}>{ts} {host} {r['service']}[{random.randint(100, 9999)}]: {tail}",
            frac, yr)


def r_syslog_nolevel(r, dt):
    """No priority, no level token anywhere -- level must come back null."""
    ts, frac, yr = ts_syslog(dt)
    host = random.choice(["combo", "node01", "gw-2", "lab-a"])
    tail = r["message"]
    if r["trace_id"]:
        tail += f" [{random.choice(TRACE_KEYS)}={r['trace_id']}]"
    elif random.random() < 0.5:
        tail += f" ({distractor()})"
    if r["latency_ms"] is not None:
        tail += f" took={r['_lat_txt']}"
    return (f"{ts} {host} {r['service']}[{random.randint(100, 99999)}]: {tail}",
            frac, yr)


def r_json_container(r, dt):
    ts, frac, yr = random.choice(
        [ts_epoch_ms, ts_epoch, ts_iso_offset, ts_dotted])(dt)
    obj = {"time": ts, "severity": random.choice(LEVEL_ALIASES[r["level"]]),
           "container": {"name": r["service"], "namespace": "prod"},
           "log": r["message"]}
    if r["trace_id"]:
        obj[random.choice(TRACE_KEYS)] = r["trace_id"]
    elif random.random() < 0.4:
        obj["ref"] = distractor()
    if r["latency_ms"] is not None:
        obj["latency"] = r["_lat_txt"]
    return json.dumps(obj), frac, yr


def r_java(r, dt):
    ts, frac, yr = ts_java(dt)
    thread = f"pool-{random.randint(1, 9)}-thread-{random.randint(1, 32)}"
    line = (f"{ts} {random.choice(LEVEL_ALIASES[r['level']])} [{thread}] "
            f"{r['service']}: {r['message']}")
    if r["trace_id"]:
        line += f" traceId={r['trace_id']}"
    elif random.random() < 0.4:
        line += f" {distractor()}"
    if r["latency_ms"] is not None:
        line += f" elapsed={r['_lat_txt']}"
    return line, frac, yr


def r_compact(r, dt):
    ts, frac, yr = ts_compact(dt)
    line = (f"{ts} {random.randint(1, 99999)} "
            f"{random.choice(LEVEL_ALIASES[r['level']])} {r['service']}: {r['message']}")
    if r["trace_id"]:
        line += f" {random.choice(TRACE_KEYS)}={r['trace_id']}"
    elif random.random() < 0.5:
        line += f" {distractor()}"
    if r["latency_ms"] is not None:
        line += f" ({r['_lat_txt']})"
    return line, frac, yr


def r_slash(r, dt):
    ts, frac, yr = ts_slash(dt)
    line = (f"{ts} {random.choice(LEVEL_ALIASES[r['level']])} "
            f"{r['service']}: {r['message']}")
    if r["trace_id"]:
        line += f" [{r['trace_id']}]"
    elif random.random() < 0.4:
        line += f" [{distractor()}]"
    if r["latency_ms"] is not None:
        line += f" took {r['_lat_txt']}"
    return line, frac, yr


def r_pipe_nolevel(r, dt):
    """Pipe-delimited component log. No level position at all."""
    ts, frac, yr = ts_pipe(dt)
    line = f"{ts}|{r['service']}|{random.randint(10**7, 10**8)}|{r['message']}"
    if r["trace_id"]:
        line += f"|{r['trace_id']}"
    elif random.random() < 0.4:
        line += f"|{distractor()}"
    if r["latency_ms"] is not None:
        line += f" cost={r['_lat_txt']}"
    return line, frac, yr


def r_bracket_noyear_nolevel(r, dt):
    """Bracketed month.day clock, process name, no level and no year."""
    ts, frac, yr = ts_md_noyear(dt)
    tail = r["message"]
    if r["trace_id"]:
        tail += f" ({random.choice(TRACE_KEYS)}: {r['trace_id']})"
    elif random.random() < 0.5:
        tail += f", {distractor()}"
    line = f"[{ts}] {r['service']} - {tail}"
    if r["latency_ms"] is not None:
        line += f", lifetime {r['_lat_txt']}"
    return line, frac, yr


def r_no_service(r, dt):
    """Level present, but the format has no service position -> service null."""
    ts, frac, yr = ts_apache(dt)
    line = f"[{ts}] [{random.choice(LEVEL_ALIASES[r['level']])}] {r['message']}"
    if r["trace_id"]:
        line += f" {random.choice(TRACE_KEYS)}={r['trace_id']}"
    elif random.random() < 0.4:
        line += f" ({distractor()})"
    if r["latency_ms"] is not None:
        line += f" rt={r['_lat_txt']}"
    return line, frac, yr


def r_access_log(r, dt):
    """No level token -- it must be derived from the HTTP status code."""
    ts, frac, yr = ts_apache(dt)
    status = r["status_code"]
    ip = ".".join(str(random.randint(1, 254)) for _ in range(4))
    # rt= carries 3 decimals of seconds, i.e. whole milliseconds. Re-derive the
    # label FROM the rendered text so the gold is always recoverable from the
    # line -- rendering a rounded value against an unrounded label would make
    # the example impossible to get right.
    rt_txt = f'{r["latency_ms"] / 1000:.3f}'
    r["latency_ms"] = int(round(float(rt_txt) * 1000))
    line = (f'{ip} - - [{ts}] "{r["_method"]} {r["_path"]} HTTP/1.1" '
            f'{status} {random.randint(80, 90000)} "-" "Mozilla/5.0" '
            f'rt={rt_txt} upstream={r["service"]}')
    if r["trace_id"]:
        line += f' trace={r["trace_id"]}'
    return line, frac, yr


# caps: (has_level, has_service, is_http), weight
RENDERERS = [
    (r_logfmt,                 True,  True,  False, 14),
    (r_syslog,                 True,  True,  False, 12),
    (r_json_container,         True,  True,  False, 12),
    (r_java,                   True,  True,  False, 12),
    (r_compact,                True,  True,  False,  8),
    (r_slash,                  True,  True,  False,  8),
    (r_access_log,             False, True,  True,  10),
    (r_syslog_nolevel,         False, True,  False, 15),
    (r_pipe_nolevel,           False, True,  False, 12),
    (r_bracket_noyear_nolevel, False, True,  False, 12),
    (r_no_service,             True,  False, False, 18),
]


def make_record(start, end, has_level, has_service, is_http):
    span = int((end - start).total_seconds())
    dt = (start + timedelta(seconds=random.randint(0, span))).replace(
        microsecond=0, tzinfo=timezone.utc)

    if has_service:
        service = random.choice(
            LOGGERS if random.random() < 0.35 else
            (PROCS + COMPONENTS if random.random() < 0.35 else SERVICES))
    else:
        service = None

    lat_txt, lat = None, None
    if random.random() < 0.12:
        lat_txt, lat = fmt_latency()

    r = {
        "level": random.choices(LEVELS, weights=[4, 17, 40, 18, 15, 6])[0]
                 if has_level else None,
        "service": service,
        "trace_id": None,
        "status_code": None,
        "latency_ms": lat,
        "message": random.choice(MESSAGES).replace("{n}", str(random.randint(1, 9999))),
        "_lat_txt": lat_txt,
    }
    if random.random() < 0.2:
        r["trace_id"] = (f"req-{rand_uuid()}" if random.random() < 0.35
                         else rand_hex(32))

    if is_http:
        status = random.choice([200, 201, 204, 301, 304, 400, 401,
                                403, 404, 429, 500, 502, 503, 504])
        r["status_code"] = status
        # ADJUDICATION L1: absent level means null. Inferring one from the
        # status code would teach context-inference in the same dataset that
        # teaches abstention. status_code carries the signal instead.
        r["level"] = None
        if r["latency_ms"] is None:
            r["latency_ms"] = random.randint(1, 5000)
        r["_method"], r["_path"] = random.choice(METHODS), random.choice(PATHS)
        r["message"] = f'{r["_method"]} {r["_path"]}'
    return r, dt


def build(n, start, end):
    fns = [x[0] for x in RENDERERS]
    weights = [x[4] for x in RENDERERS]
    rows = []
    for _ in range(n):
        fn = random.choices(fns, weights=weights)[0]
        _, has_level, has_service, is_http, _ = next(
            x for x in RENDERERS if x[0] is fn)
        rec, dt = make_record(start, end, has_level, has_service, is_http)
        raw, frac, year_known = fn(rec, dt)
        out = {f: rec[f] for f in FIELDS if f != "timestamp"}
        out = {"timestamp": canon_ts(dt, frac, year_known), **out}
        rows.append({"input": raw, "output": {f: out[f] for f in FIELDS}})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=20000)
    ap.add_argument("--test", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--prefix", default="")
    args = ap.parse_args()

    random.seed(args.seed)
    train = build(args.train, datetime(2026, 1, 1), datetime(2026, 5, 31))
    random.seed(args.seed + 1000)
    test = build(args.test, datetime(2026, 6, 1), datetime(2026, 7, 31))

    for name, rows in [("train_v2.jsonl", train), ("test_v2.jsonl", test)]:
        path = args.prefix + name
        with open(path, "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        nulls = {f: sum(1 for r in rows if r["output"][f] is None) for f in FIELDS}
        print(f"wrote {path}: {len(rows)} rows")
        print("  null rate: " + "  ".join(
            f"{f}={nulls[f]/len(rows):.0%}" for f in FIELDS if nulls[f]))


if __name__ == "__main__":
    main()
