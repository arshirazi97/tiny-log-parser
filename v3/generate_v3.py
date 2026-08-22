#!/usr/bin/env python3
"""Targeted synthetic renderers for the two families v2 fails on.

    python3 v3/generate_v3.py --n 5000 --out v3/synth_v3.jsonl

New file, not an edit to the frozen `generate_v2.py` -- FREEZE_P0.txt anticipates
exactly this ("the P2 generator additions land in a NEW file").

These renderers exist because the failures they target are 0.011% of real
Loghub-2.0 lines and cannot be learned from it at any practical scale, while a
generator knows the answer by construction and can emit them at any density.
Both families are measured, not guessed: on the P1 corpus they are 22 of the
23 lines the v2 fine-tune could recover by matching the parser.

F1  thread-then-logger.  The thread descriptor is the tempting answer and the
    logger is the right one. Two shapes, both real:
      [main] org.apache.hadoop.mapred.MapTask: ...        -> the dotted logger
      [SendWorker:1889:QuorumCnxManager$SendWorker@688]    -> the class before @
    S1 forbids shortening the dotted path to its last segment, so the full path
    is the label and single-segment loggers are generated too.

F2  duration in prose.  `latency_ms` is null when the number sits in the message
    text, and non-null only in a structural position. Both are generated, in a
    declared ratio, so the model learns the distinction rather than "always
    null" -- which is what a natural-frequency sample would teach.
"""
import argparse, json, random, sys

sys.path.insert(0, ".")
from schema_v2 import LEVELS

# ---------------------------------------------------------------- vocabularies

PKG = ["org.apache.hadoop", "org.apache.spark", "org.apache.zookeeper",
       "com.acme.ingest", "io.netty.channel", "org.eclipse.jetty.server",
       "net.corda.node", "org.postgresql.jdbc"]
SUB = ["mapred", "mapreduce.v2.app.rm", "ipc", "metrics2.impl", "server.quorum",
       "storage", "scheduler", "executor", "util", "hdfs", "security.token"]
CLS = ["MapTask", "YarnChild", "RMContainerAllocator", "MetricsSystemImpl",
       "TaskAttemptListenerImpl", "LeaseRenewer", "DiskBlockManager",
       "CoarseGrainedExecutorBackend", "QuorumCnxManager$SendWorker",
       "QuorumCnxManager$RecvWorker", "NIOServerCnxn", "FastLeaderElection",
       "SessionTrackerImpl", "CommitProcessor", "FileTxnLog", "Follower",
       "Leader", "Environment", "JobHistoryEventHandler", "RackResolver"]

# thread names chosen to be maximally distracting: they look like components
THREAD = ["main", "Thread-147", "communication thread", "AsyncDispatcher event handler",
          "Socket Reader #1 for port 32070", "RMCommunicator Allocator",
          "IPC Server handler 3 on 8020", "SendWorker", "RecvWorker",
          "NIOServerCxn.Factory", "SyncThread:1", "CommitProcessor:1",
          "SessionTracker", "pool-4-thread-6", "qtp1234567-42", "ProcessThread(sid:2 cport:-1)"]

MSG = ["Retrying connect to server: {host}. Already tried {n} time(s)",
       "Stopping {cls} metrics system", "Recovering task task_{id}_m_{n:06d}",
       "Closed socket connection for client /{ip}:{port}",
       "Received connection request /{ip}:{port}",
       "Assigned container container_{id}_{n:02d} to attempt",
       "block blk_{big} received exception java.io.IOException: Broken pipe",
       "Notification time out: {n}", "Shutdown called", "exited loop!",
       "Creating new log file: log.{big}", "caught end of stream exception"]

# F2: durations in prose -- gold latency_ms is null for every one of these
PROSE_DUR = [
    "finished in {v} s", "failed in {v} s", "completed in {v}s",
    "{ms} millis timeout left", "{ms} millis timeout while waiting for channel",
    "Sleeping for {ms}ms before retrying again", "timeout of {ms}ms exceeded",
    "elapsedRealtime(): {ms}", "Commit interval {sec} seconds",
    "retry in {sec}s", "lifetime {mm}:{ss}", "backoff {sec}s before next attempt",
]
# F2 counterpart: a structural duration -- gold latency_ms IS set.
#
# Only `time: <seconds>` appears here. That is the single structural form
# ADJUDICATION F4 defines and the only one `rule_parser.py` extracts. Earlier
# drafts also emitted `duration=`, `rt=`, `elapsed=` and `took=`; the parser
# returns null for all of them, so those labels would have contradicted both the
# teacher for the real 75% and the convention the eval gold is written against.
# Validated: the parser now agrees with these labels on 100% of F2b records.
STRUCT_DUR = [("time: {s}", "s")]


def ip():   return ".".join(str(random.randint(1, 254)) for _ in range(4))
def big():  return random.randint(10**12, 10**18)


def logger():
    """A dotted logger. Single-segment sometimes, so S1 is not just 'has dots'."""
    if random.random() < 0.15:
        return random.choice(CLS)
    depth = random.choice([1, 1, 2])
    parts = [random.choice(PKG)] + random.sample(SUB, depth - 1 if depth > 1 else 0)
    return ".".join(parts + [random.choice(CLS)])


def message():
    t = random.choice(MSG)
    return t.format(host=f"host-{random.randint(1,99)}.internal", n=random.randint(0, 60),
                    ip=ip(), port=random.randint(1024, 65535), cls=random.choice(CLS),
                    id=random.randint(10**12, 10**13), big=big())


def stamp():
    y, mo, d = random.randint(2015, 2024), random.randint(1, 12), random.randint(1, 28)
    h, mi, s = random.randint(0, 23), random.randint(0, 59), random.randint(0, 59)
    ms = random.randint(0, 999)
    return (f"{y}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d},{ms:03d}",
            f"{y}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}.{ms:03d}Z")


def rec(inp, ts, level, service, msg, lat=None):
    return {"family": None, "input": inp,
            "output": {"timestamp": ts, "level": level, "service": service,
                       "trace_id": None, "status_code": None,
                       "latency_ms": lat, "message": msg}}


# ------------------------------------------------------------------ family F1

def f1_thread_then_logger():
    """`... LEVEL [thread] logger: message` -- the logger is the service."""
    raw_ts, iso = stamp()
    lvl = random.choice(LEVELS)
    alias = {"WARNING": "WARN", "ERROR": "ERROR", "INFO": "INFO",
             "DEBUG": "DEBUG", "TRACE": "TRACE", "FATAL": "FATAL"}[lvl]
    th, lg, msg = random.choice(THREAD), logger(), message()
    line = f"{raw_ts} {alias} [{th}] {lg}: {msg}"
    r = rec(line, iso, lvl, lg, msg)
    r["family"] = "F1a_thread_then_logger"
    return r


def f1_class_in_thread_bracket():
    """`... - LEVEL  [thread:Class@line] - message` -- the class before @."""
    raw_ts, iso = stamp()
    lvl = random.choice(LEVELS)
    alias = {"WARNING": "WARN", "ERROR": "ERROR", "INFO": "INFO",
             "DEBUG": "DEBUG", "TRACE": "TRACE", "FATAL": "FATAL"}[lvl]
    cls, msg = random.choice(CLS), message()
    pre = random.choice([
        random.choice(THREAD),
        f"{random.choice(THREAD)}:{random.randint(1000, 10**12)}",
        f"/{ip()}:{random.randint(1024, 9999)}",
        f"QuorumPeer[myid={random.randint(1,5)}]/0:0:0:0:0:0:0:0:{random.randint(2181,2189)}",
    ])
    line = f"{raw_ts} - {alias}  [{pre}:{cls}@{random.randint(50, 1200)}] - {msg}"
    r = rec(line, iso, lvl, cls, msg)
    r["family"] = "F1b_class_in_thread_bracket"
    return r


# ------------------------------------------------------------------ family F2

def f2_prose_duration():
    """A duration in the message text. gold latency_ms is null."""
    raw_ts, iso = stamp()
    lvl = random.choice(LEVELS)
    alias = {"WARNING": "WARN", "ERROR": "ERROR", "INFO": "INFO",
             "DEBUG": "DEBUG", "TRACE": "TRACE", "FATAL": "FATAL"}[lvl]
    lg = logger()
    tail = random.choice(PROSE_DUR).format(
        v=f"{random.uniform(0.001, 900):.3f}", ms=random.randint(0, 500000),
        sec=random.randint(1, 300), mm=f"{random.randint(0,59):02d}",
        ss=f"{random.randint(0,59):02d}")
    msg = f"{message()} {tail}"
    line = f"{raw_ts} {alias} [{random.choice(THREAD)}] {lg}: {msg}"
    r = rec(line, iso, lvl, lg, msg, lat=None)     # <- the whole point
    r["family"] = "F2a_prose_duration_null"
    return r


def f2_structural_duration():
    """A duration in a structural position. gold latency_ms IS set.

    Rendered OpenStack-shaped, because that is the only place this schema puts a
    structural latency: `rule_parser.m_openstack` extracts `time: <seconds>` and
    no other matcher extracts a duration at all. Generating `duration=`/`rt=` in
    a Java-shaped line -- as an earlier draft did -- produced labels the parser
    scores 0% on, i.e. a convention that exists nowhere in the schema.

    This is the positive class for `latency_ms`. Without it the synthetic set
    teaches "always null", which is the failure the amendment warned about.
    """
    svc = random.choice(["nova.osapi_compute.wsgi.server", "nova.api.openstack.wsgi",
                         "nova.compute.manager", "keystonemiddleware.auth_token",
                         "nova.virt.libvirt.driver", "nova.metadata.wsgi.server"])
    logf = random.choice(["nova-api", "nova-compute", "nova-scheduler"])
    y, mo, d = random.randint(2015, 2024), random.randint(1, 12), random.randint(1, 28)
    h, mi, sec = random.randint(0, 23), random.randint(0, 59), random.randint(0, 59)
    ms = random.randint(0, 999)
    iso = f"{y}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{sec:02d}.{ms:03d}Z"
    head = (f"{logf}.log.1.{y}-{mo:02d}-{d:02d}_{h:02d}:{mi:02d}:{sec:02d} "
            f"{y}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{sec:02d}.{ms:03d} "
            f"{random.randint(1000, 30000)}")
    lvl = random.choice(["INFO", "WARNING", "ERROR", "DEBUG"])
    req = "req-" + "-".join(
        "".join(random.choice("0123456789abcdef") for _ in range(n))
        for n in (8, 4, 4, 4, 12))

    # F4: seconds -> ms, not rounded. The parser computes float(s) * 1000, which
    # can land on 5344.400000000001 for a decimal that F4 says should read
    # 5344.4. Only emit durations that survive that arithmetic exactly, so the
    # label is both clean and identical to what the teacher produces.
    # Exactly 7 decimals: that is what real OpenStack emits (`time: 0.2598419`),
    # and validate_v2 can only verify a duration rendered at 3 or 7 dp.
    for _ in range(64):
        secs_txt = f"{random.uniform(0.0001, 30):.7f}"
        prod = float(secs_txt) * 1000
        if prod == round(prod, 6):
            break
    lat = prod
    lat = int(lat) if lat == int(lat) else lat

    status = random.choice([200, 200, 201, 204, 400, 404, 500]) if random.random() < 0.65 else None
    # real OpenStack quotes the request line: "GET /v2/... HTTP/1.1"
    body = (f'"{random.choice(["GET", "POST", "DELETE"])} '
            f'/v2/{random.randint(10**6, 10**7)}/servers HTTP/1.1"')
    tail = f"status: {status} len: {random.randint(200, 9000)} " if status else ""
    msg = f"{body} {tail}time: {secs_txt}".strip()
    line = f"{head} {lvl} {svc} [{req} - - - - -] {msg}"

    r = rec(line, iso, lvl, svc, msg, lat=lat)
    r["output"]["trace_id"] = req
    r["output"]["status_code"] = status
    r["family"] = "F2b_structural_duration_set"
    return r


# mix declared here, not tuned later
GENS = [(f1_thread_then_logger, 0.30), (f1_class_in_thread_bracket, 0.30),
        (f2_prose_duration, 0.28), (f2_structural_duration, 0.12)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--out", default="v3/synth_v3.jsonl")
    ap.add_argument("--seed", type=int, default=20260823)
    a = ap.parse_args()
    random.seed(a.seed)

    fns = [f for f, _ in GENS]
    wts = [w for _, w in GENS]
    rows, seen = [], set()
    guard = 0
    while len(rows) < a.n and guard < a.n * 40:
        guard += 1
        r = random.choices(fns, weights=wts)[0]()
        if r["input"] in seen:
            continue
        seen.add(r["input"])
        rows.append(r)

    with open(a.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    from collections import Counter
    c = Counter(r["family"] for r in rows)
    print(f"wrote {a.out}: {len(rows)} records (seed {a.seed})")
    for k, v in sorted(c.items()):
        print(f"  {k:32} {v:5}  {v/len(rows):5.1%}")
    nn = sum(1 for r in rows if r["output"]["latency_ms"] is not None)
    print(f"  latency_ms non-null              {nn:5}  {nn/len(rows):5.1%}")


if __name__ == "__main__":
    main()
