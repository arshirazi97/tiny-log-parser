"""
Synthetic log-normalization dataset generator.

Strategy: build the CANONICAL record first, then render it into a messy
real-world log line. The canonical record is the label -- no annotation needed.

Output: JSONL with {"input": "<raw log line>", "output": {<canonical record>}}
"""

import argparse
import json
import random
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------
# Canonical schema
# --------------------------------------------------------------------------
# timestamp   : ISO8601 UTC, second precision, "Z" suffix   e.g. 2026-08-04T11:23:45Z
# level       : one of CRITICAL ERROR WARNING INFO DEBUG
# service     : lowercase service name
# trace_id    : 32-char lowercase hex, or null if absent
# status_code : int, or null if not an HTTP event
# latency_ms  : int milliseconds, or null if absent
# message     : the human-readable message, whitespace-collapsed

LEVELS = ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]

# Aliases the raw line may use. Includes syslog numeric severities.
LEVEL_ALIASES = {
    "CRITICAL": ["CRITICAL", "CRIT", "FATAL", "critical", "fatal", "C", "2"],
    "ERROR":    ["ERROR", "ERR", "error", "E", "3"],
    "WARNING":  ["WARNING", "WARN", "warning", "warn", "W", "4"],
    "INFO":     ["INFO", "info", "I", "NOTICE", "notice", "6", "5"],
    "DEBUG":    ["DEBUG", "debug", "DBG", "D", "7"],
}

SERVICES = [
    "auth-api", "payments", "checkout", "user-profile", "search-indexer",
    "notification-worker", "image-resizer", "session-store", "billing",
    "webhook-dispatcher", "recommendation", "inventory", "cdn-edge",
]

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
]

PATHS = [
    "/api/v1/users", "/api/v1/orders", "/healthz", "/api/v2/search",
    "/checkout/session", "/webhooks/stripe", "/assets/logo.svg", "/api/v1/auth/token",
]
METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]


def rand_hex(n):
    return "".join(random.choice("0123456789abcdef") for _ in range(n))


def make_record(rng_start, rng_end):
    """Build one canonical record."""
    span = int((rng_end - rng_start).total_seconds())
    ts = rng_start + timedelta(seconds=random.randint(0, span))
    ts = ts.replace(microsecond=0, tzinfo=timezone.utc)

    level = random.choices(LEVELS, weights=[3, 15, 20, 45, 17])[0]
    msg = random.choice(MESSAGES).replace("{n}", str(random.randint(1, 9999)))

    return {
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "level": level,
        "service": random.choice(SERVICES),
        "trace_id": rand_hex(32) if random.random() < 0.55 else None,
        "status_code": None,
        "latency_ms": random.randint(1, 8000) if random.random() < 0.5 else None,
        "message": msg,
        "_dt": ts,  # scratch, stripped before writing
    }


# --------------------------------------------------------------------------
# Timestamp renderers -- each returns a differently-formatted string
# --------------------------------------------------------------------------

def ts_iso_offset(dt):
    off = random.choice([-8, -5, 0, 1, 5, 9])
    local = dt + timedelta(hours=off)
    sign = "+" if off >= 0 else "-"
    return local.strftime(f"%Y-%m-%dT%H:%M:%S{sign}{abs(off):02d}:00")


def ts_syslog(dt):
    # RFC3164: no year, day space-padded
    return dt.strftime("%b %e %H:%M:%S").replace("  ", " " if dt.day >= 10 else "  ")


def ts_epoch(dt):
    return str(int(dt.timestamp()))


def ts_epoch_ms(dt):
    return str(int(dt.timestamp() * 1000) + random.randint(0, 999))


def ts_apache(dt):
    off = random.choice([-8, -5, 0, 2])
    local = dt + timedelta(hours=off)
    sign = "+" if off >= 0 else "-"
    return local.strftime(f"%d/%b/%Y:%H:%M:%S {sign}{abs(off):02d}00")


def ts_java(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S,") + f"{random.randint(0,999):03d}"


def fmt_latency(ms):
    """Render latency in one of several units -- forces unit conversion."""
    style = random.choice(["ms", "s", "plain", "us"])
    if style == "ms":
        return f"{ms}ms"
    if style == "s":
        return f"{ms/1000:.3f}s"
    if style == "us":
        return f"{ms*1000}us"
    return str(ms)


# --------------------------------------------------------------------------
# Line renderers
# --------------------------------------------------------------------------

def render_logfmt(r):
    parts = [
        f"ts={ts_iso_offset(r['_dt'])}",
        f"level={random.choice(LEVEL_ALIASES[r['level']])}",
        f"service={r['service']}",
    ]
    if r["trace_id"]:
        parts.append(f"{random.choice(TRACE_KEYS)}={r['trace_id']}")
    if r["latency_ms"] is not None:
        parts.append(f"duration={fmt_latency(r['latency_ms'])}")
    parts.append(f'msg="{r["message"]}"')
    random.shuffle(parts)
    return " ".join(parts)


def render_syslog(r):
    sev = {"CRITICAL": 2, "ERROR": 3, "WARNING": 4, "INFO": 6, "DEBUG": 7}[r["level"]]
    pri = 8 * 16 + sev
    host = f"{random.choice(['web','app','edge'])}-{random.randint(1,40):02d}"
    tail = r["message"]
    if r["trace_id"]:
        tail += f" [{random.choice(TRACE_KEYS)}={r['trace_id']}]"
    if r["latency_ms"] is not None:
        tail += f" took={fmt_latency(r['latency_ms'])}"
    return f"<{pri}>{ts_syslog(r['_dt'])} {host} {r['service']}[{random.randint(100,9999)}]: {tail}"


def render_json_container(r):
    obj = {
        "time": random.choice([ts_epoch_ms(r["_dt"]), ts_iso_offset(r["_dt"])]),
        "severity": random.choice(LEVEL_ALIASES[r["level"]]),
        "kubernetes": {"container_name": r["service"], "namespace": "prod"},
        "log": r["message"],
    }
    if r["trace_id"]:
        obj[random.choice(TRACE_KEYS)] = r["trace_id"]
    if r["latency_ms"] is not None:
        obj["latency"] = fmt_latency(r["latency_ms"])
    return json.dumps(obj)


def render_java(r):
    thread = f"http-nio-8080-exec-{random.randint(1,32)}"
    cls = "com." + r["service"].replace("-", ".") + ".Handler"
    line = f"{ts_java(r['_dt'])} {random.choice(LEVEL_ALIASES[r['level']])} [{thread}] {cls} - {r['message']}"
    if r["trace_id"]:
        line += f" traceId={r['trace_id']}"
    if r["latency_ms"] is not None:
        line += f" elapsed={fmt_latency(r['latency_ms'])}"
    return line


def render_bracket(r):
    line = f"[{ts_epoch(r['_dt'])}] [{random.choice(LEVEL_ALIASES[r['level']])}] [{r['service']}] {r['message']}"
    if r["trace_id"]:
        line += f" ({random.choice(TRACE_KEYS)}: {r['trace_id']})"
    if r["latency_ms"] is not None:
        line += f" <{fmt_latency(r['latency_ms'])}>"
    return line


def render_access_log(r):
    """
    nginx combined. No explicit level -- it MUST be derived from status code:
      5xx -> ERROR,  4xx -> WARNING,  else INFO
    This mutates the record, so it returns the corrected canonical too.
    """
    status = random.choice([200, 201, 204, 301, 304, 400, 401, 403, 404, 429, 500, 502, 503, 504])
    r["status_code"] = status
    r["level"] = "ERROR" if status >= 500 else ("WARNING" if status >= 400 else "INFO")
    if r["latency_ms"] is None:
        r["latency_ms"] = random.randint(1, 5000)

    method, path = random.choice(METHODS), random.choice(PATHS)
    r["message"] = f"{method} {path}"
    ip = ".".join(str(random.randint(1, 254)) for _ in range(4))
    line = (
        f'{ip} - - [{ts_apache(r["_dt"])}] "{method} {path} HTTP/1.1" '
        f'{status} {random.randint(80, 90000)} "-" "Mozilla/5.0" '
        f'rt={r["latency_ms"]/1000:.3f} upstream={r["service"]}'
    )
    if r["trace_id"]:
        line += f' trace={r["trace_id"]}'
    return line


RENDERERS = [
    render_logfmt, render_syslog, render_json_container,
    render_java, render_bracket, render_access_log,
]


def build(n, start, end):
    rows = []
    for _ in range(n):
        rec = make_record(start, end)
        raw = random.choice(RENDERERS)(rec)
        rec.pop("_dt")
        rows.append({"input": raw, "output": rec})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=5000)
    ap.add_argument("--test", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    random.seed(args.seed)

    # Disjoint time windows for train vs test -- prevents timestamp memorization
    train = build(args.train, datetime(2026, 1, 1), datetime(2026, 5, 31))
    random.seed(args.seed + 1000)
    test = build(args.test, datetime(2026, 6, 1), datetime(2026, 7, 31))

    for name, rows in [("train.jsonl", train), ("test.jsonl", test)]:
        with open(name, "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        print(f"wrote {name}: {len(rows)} rows")


if __name__ == "__main__":
    main()
