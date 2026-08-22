#!/usr/bin/env python3
"""Browser labelling UI for the P1 corpus. Local, no dependencies.

    python real-eval/label_ui.py
    -> open http://localhost:8765

Same output as label.py -- appends to labels_p1.jsonl and ambiguous_p1.jsonl --
so the two are interchangeable and a session started in one can finish in the
other.

Three fields per line, not seven:

  timestamp, level, service   you decide. These need judgement and no
                              third-party annotation of them exists.
  message                     filled afterwards from Loghub-2.0's `Content`
                              column, which IS a third-party annotation of
                              exactly this field. See fill_message_from_loghub.py.
  trace/status/latency        null unless you open the extras panel. Non-null
                              on ~5 of 262 lines, all OpenStack.

The UI shows the raw line, the rules for that line's system, and clickable
tokens so service can be copied rather than retyped. It never proposes a value:
every field starts empty, and the per-system panel is quoted from
ADJUDICATION.md, which is the rulebook the labeller is meant to apply.
"""
import argparse, json, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

FIELDS = ["timestamp", "level", "service", "trace_id",
          "status_code", "latency_ms", "message"]

# quoted from ADJUDICATION.md -- the rulebook, not answers
HINTS = {
 "Zookeeper": ("<code>YYYY-MM-DD hh:mm:ss,SSS</code> &rarr; <code>YYYY-MM-DDThh:mm:ss.SSSZ</code>",
   "written in the line (<code>WARN</code>&rarr;<code>WARNING</code>)",
   "S1b &mdash; the class immediately before <code>@&lt;num&gt;</code>. The leading token in the bracket is the <em>thread</em>, not the logger."),
 "Hadoop": ("<code>YYYY-MM-DD hh:mm:ss,SSS</code> &rarr; <code>YYYY-MM-DDThh:mm:ss.SSSZ</code>",
   "written in the line", "S1 &mdash; the full dotted logger, as written. Do not shorten to the last segment."),
 "HDFS": ("<code>yymmdd hhmmss</code> &rarr; <code>20yy-mm-ddThh:mm:ssZ</code> &mdash; the date is six digits with no separators",
   "written in the line", "S1 &mdash; the full dotted logger, e.g. the <code>a.b$C</code> form."),
 "Spark": ("<code>yy/mm/dd hh:mm:ss</code> &rarr; <code>20yy-mm-ddThh:mm:ssZ</code> &mdash; <strong>year first</strong>, not day",
   "written in the line", "S1 &mdash; the logger before the colon."),
 "OpenStack": ("<code>YYYY-MM-DD hh:mm:ss.SSS</code> &rarr; <code>YYYY-MM-DDThh:mm:ss.SSSZ</code> &mdash; use the second timestamp, not the one inside the filename",
   "written in the line",
   "S4 &mdash; the logger <em>after</em> the PID. The line opens with a log <em>filename</em>, which is not the service."),
 "HealthApp": ("<code>yyyymmdd-hh:mm:ss:SSS</code> &rarr; <code>yyyy-mm-ddThh:mm:ss.SSSZ</code> &mdash; the last <code>:</code> is sub-seconds",
   "<strong>null</strong> &mdash; no level position (L1)", "the component between the first pair of pipes."),
 "Apache": ("<code>[Day Mon DD hh:mm:ss YYYY]</code> &rarr; <code>YYYY-MM-DDThh:mm:ssZ</code>",
   "<code>[notice]</code>&rarr;<code>INFO</code>, <code>[error]</code>&rarr;<code>ERROR</code> (L2)",
   "S3 &mdash; <strong>null</strong>. Never <code>apache</code>, <code>httpd</code> or <code>unknown</code>; inventing one is a hallucination."),
 "Linux": ("<code>Mon DD hh:mm:ss</code> &rarr; <code>1900-MM-DDThh:mm:ssZ</code> &mdash; no year in the line, so the <strong>1900</strong> sentinel (T1)",
   "<strong>null</strong> &mdash; no level position (L1). <code>combo</code> is the hostname.",
   "S2 &mdash; the process; drop <code>(pam_unix)</code> and <code>[pid]</code>. S2b &mdash; a <em>version</em> stays."),
 "OpenSSH": ("<code>Mon DD hh:mm:ss</code> &rarr; <code>1900-MM-DDThh:mm:ssZ</code> &mdash; <strong>1900</strong> sentinel (T1)",
   "<strong>null</strong> (L1). <code>authentication failure</code> is prose, not a level (L3).",
   "S2 &mdash; the daemon before <code>[pid]</code>. The hostname is not the service."),
 "Proxifier": ("<code>[mm.dd hh:mm:ss]</code> &rarr; <code>1900-mm-ddThh:mm:ssZ</code> &mdash; <strong>1900</strong> sentinel (T1)",
   "<strong>null</strong> (L1)",
   "S2c &mdash; the architecture marker <strong>stays</strong> (e.g. a trailing <code>*64</code>)."),
}
GLOBAL = ("Every timestamp is rewritten, never copied: <code>T</code> between date and time, "
          "<code>,</code>&rarr;<code>.</code> for sub-seconds (kept exactly, never padded or rounded), "
          "<code>Z</code> on the end (T2, T3).")

PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>P1 labelling</title><style>
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
     background:#12141a;color:#e6e8ee}
.wrap{max-width:980px;margin:0 auto;padding:22px 20px 90px}
header{display:flex;align-items:baseline;gap:14px;margin-bottom:6px}
h1{font-size:15px;font-weight:600;margin:0;letter-spacing:.02em}
.sys{font-size:13px;padding:2px 9px;border-radius:99px;background:#26304a;color:#9fc0ff}
.count{margin-left:auto;font-size:13px;color:#79808f;font-variant-numeric:tabular-nums}
.bar{height:3px;background:#232734;border-radius:2px;overflow:hidden;margin:10px 0 20px}
.bar i{display:block;height:100%;background:#5b8cff;transition:width .25s}
.raw{background:#0b0d12;border:1px solid #232734;border-left:3px solid #5b8cff;
     border-radius:6px;padding:15px 16px;font:13.5px/1.7 ui-monospace,SFMono-Regular,Menlo,monospace;
     word-break:break-all;margin-bottom:6px}
.tok{cursor:pointer;border-radius:3px;padding:1px 2px;transition:background .1s}
.tok:hover{background:#28304a}
.tokhint{font-size:12px;color:#6c7382;margin-bottom:20px}
.f{margin-bottom:17px}
label.k{display:block;font-size:12px;letter-spacing:.09em;text-transform:uppercase;
        color:#8b93a4;margin-bottom:6px;font-weight:600}
input[type=text]{width:100%;background:#0b0d12;border:1px solid #2b3040;border-radius:6px;
     color:#e6e8ee;padding:10px 12px;font:14px ui-monospace,Menlo,monospace}
input[type=text]:focus{outline:none;border-color:#5b8cff;background:#0d1018}
input.bad{border-color:#c8553d}
.hint{font-size:12.5px;color:#79808f;margin-top:6px}
.hint code{background:#1b1f2b;padding:1px 5px;border-radius:3px;color:#a9b4cc;font-size:12px}
.lv{display:flex;flex-wrap:wrap;gap:7px}
.lv button{background:#1a1e29;border:1px solid #2b3040;color:#c3c9d6;border-radius:6px;
     padding:7px 13px;font-size:13px;cursor:pointer;font-family:inherit}
.lv button:hover{border-color:#4a5170}
.lv button.on{background:#5b8cff;border-color:#5b8cff;color:#0b0d12;font-weight:600}
.lv button.null{color:#8b93a4;font-style:italic}
.lv button.null.on{background:#495066;border-color:#495066;color:#fff;font-style:normal}
.act{position:fixed;left:0;right:0;bottom:0;background:#171a22;border-top:1px solid #262b38;
     padding:13px 20px}
.act .in{max-width:980px;margin:0 auto;display:flex;gap:10px;align-items:center}
button.p{background:#5b8cff;border:0;color:#0b0d12;font-weight:600;border-radius:6px;
     padding:11px 26px;font-size:14px;cursor:pointer;font-family:inherit}
button.p:disabled{background:#2b3040;color:#61697a;cursor:not-allowed}
button.s{background:transparent;border:1px solid #2b3040;color:#9aa2b1;border-radius:6px;
     padding:11px 16px;font-size:13px;cursor:pointer;font-family:inherit}
button.s:hover{border-color:#3d4457}
.kbd{margin-left:auto;font-size:12px;color:#5f6675}
.kbd b{background:#232734;padding:2px 6px;border-radius:3px;color:#98a0b0;font-weight:500}
details{margin:4px 0 20px}summary{cursor:pointer;font-size:13px;color:#79808f}
.ex{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:12px}
.done{text-align:center;padding:80px 20px}
.done h2{font-size:20px;margin:0 0 10px}
.warn{background:#2a2118;border:1px solid #5a4426;color:#e0b978;border-radius:6px;
      padding:11px 14px;font-size:13px;margin-bottom:18px}
</style></head><body><div class=wrap id=app>loading…</div>
<div class=act id=actbar style="display:none"><div class=in>
  <button class=p id=save>Save &amp; next</button>
  <button class=s id=flag>Flag ambiguous</button>
  <button class=s id=undo>Undo last</button>
  <span class=kbd><b>&crarr;</b> save &nbsp; <b>0-6</b> level &nbsp; <b>click</b> a token to copy</span>
</div></div>
<script>
let R=null,lvl=undefined,extras=false,U='';
const LEVELS=[null,"TRACE","DEBUG","INFO","WARNING","ERROR","FATAL"];
const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const ISO=/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;

async function load(){
  R=await (await fetch('/api/next')).json();
  if(R.done){document.getElementById('actbar').style.display='none';
    app.innerHTML=`<div class=done><h2>${R.labelled} lines labelled</h2>
      <p style="color:#79808f">Target was ${R.target}. Nothing left in scope.</p>
      <p style="color:#79808f;font-size:13px">Next: fill <code>message</code> from Loghub, then run Gate A.</p></div>`;
    return;}
  document.getElementById('actbar').style.display='block';
  lvl=undefined;extras=false;
  U='_'+R.id;
  const toks=R.raw.split(/(\s+)/).map(t=>t.trim()?`<span class=tok>${esc(t)}</span>`:esc(t)).join('');
  const h=R.hint;
  app.innerHTML=`
  <header><h1>P1 labelling</h1><span class=sys>${R.source}</span>
    <span class=count>${R.n} of ${R.target}</span></header>
  <div class=bar><i style="width:${100*R.n/R.target}%"></i></div>
  ${R.warn?`<div class=warn>${R.warn}</div>`:''}
  <div class=raw id="raw">${toks}</div>
  <div class=tokhint>Click any token above to copy it into the focused box.</div>

  <div class=f><label class=k for="ts${U}">timestamp</label>
    <input type=text id="ts${U}" spellcheck=false placeholder="YYYY-MM-DDTHH:MM:SS[.sss]Z" autocomplete=off>
    <div class=hint id=tshint>${h[0]}</div></div>

  <div class=f><label class=k>level</label><div class=lv id=lv></div>
    <div class=hint>${h[1]}</div></div>

  <div class=f><label class=k for="svc${U}">service</label>
    <input type=text id="svc${U}" spellcheck=false placeholder="(leave empty for null)" autocomplete=off>
    <div class=hint>${h[2]}</div></div>

  <details id=exd><summary>trace_id / status_code / latency_ms &mdash; null unless the line really has them</summary>
    <div class=ex>
      <div><label class=k for="tr${U}">trace_id</label><input type=text id="tr${U}" autocomplete=off spellcheck=false></div>
      <div><label class=k for="st${U}">status_code</label><input type=text id="st${U}" autocomplete=off spellcheck=false></div>
      <div><label class=k for="la${U}">latency_ms</label><input type=text id="la${U}" autocomplete=off spellcheck=false></div>
    </div></details>
  <div class=hint style="margin-top:-8px">${GLOBALHINT}</div>`;

  const lv=document.getElementById('lv');
  LEVELS.forEach((L,i)=>{const b=document.createElement('button');
    b.textContent=L===null?'null':L; b.className=L===null?'null':'';
    b.onclick=()=>{lvl=L;[...lv.children].forEach(c=>c.classList.remove('on'));b.classList.add('on');};
    lv.appendChild(b);});

  let focused=document.getElementById('ts'+U);
  ['ts','svc','tr','st','la'].forEach(id=>document.getElementById(id+U)
      .addEventListener('focus',e=>focused=e.target));
  document.getElementById('raw').onclick=e=>{
    if(!e.target.classList.contains('tok'))return;
    const t=e.target.textContent;
    focused.value = focused.value ? focused.value+' '+t : t;
    focused.focus(); check();};
  document.getElementById('ts'+U).addEventListener('input',check);
  ['ts','svc','tr','st','la'].forEach(id=>document.getElementById(id+U).value='');
  document.getElementById('ts'+U).focus();
}
function check(){const t=document.getElementById('ts'+U);
  t.classList.toggle('bad', t.value.length>0 && !ISO.test(t.value));}

async function save(){
  const g=id=>{const v=document.getElementById(id+U).value.trim();
    return (v===''||v.toLowerCase()==='null')?null:v;};
  const ts=g('ts');
  if(ts===null){alert('timestamp is required');return;}
  if(!ISO.test(ts)){alert('timestamp must match YYYY-MM-DDThh:mm:ss[.sss]Z\n\nT between date and time, . for sub-seconds, Z on the end.\n\nRead the values off THIS line, not from the grey hint.');return;}
  const hms=ts.slice(11,19);
  // HDFS packs the clock as 211158 and HealthApp as 15:32:58:333, so compare
  // with separators stripped too -- otherwise a correct answer is refused
  const strip=x=>x.replace(/[:.]/g,'');
  if(!R.raw.includes(hms) && !strip(R.raw).includes(strip(hms))){
    alert('That time ('+hms+') does not appear anywhere in this line.\n\nThe line is:\n'+R.raw+'\n\nRead the clock time off THIS line.');return;}
  if(lvl===undefined){alert('pick a level (choose "null" if the line has no level token)');return;}
  let svc=g('svc'); if(svc)svc=svc.replace(/[:\s]+$/,'');
  if(svc && !R.raw.includes(svc)){
    alert('That service ('+svc+') does not appear anywhere in this line.\n\nThe line is:\n'
          +R.raw+'\n\nIf the box holds a value from a previous line, clear it.');return;}
  await fetch('/api/label',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:R.id,label:{timestamp:ts,level:lvl,service:svc,
      trace_id:g('tr'),status_code:g('st'),latency_ms:g('la'),message:null}})});
  load();
}
document.getElementById('save').onclick=()=>save().catch(e=>alert('save failed: '+e));
document.getElementById('flag').onclick=async()=>{
  const note=prompt('why is this line ambiguous?','');
  if(note===null)return;
  await fetch('/api/flag',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:R.id,note:note||'ambiguous'})}); load();};
document.getElementById('undo').onclick=async()=>{
  await fetch('/api/undo',{method:'POST'}); load();};
document.addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();save().catch(e=>alert('save failed: '+e));}
  if(/^[0-6]$/.test(e.key)&&e.target.tagName!=='INPUT'){
    document.getElementById('lv').children[+e.key].click();}});
window.onerror=(m,src,l,c,e)=>{document.body.insertAdjacentHTML('afterbegin',
  '<div style="background:#5a2222;color:#ffd7d7;padding:10px 14px;font:13px monospace">JS error: '+m+' (line '+l+')</div>');};
load();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self._send(200, PAGE.replace("${GLOBALHINT}", GLOBAL), "text/html; charset=utf-8")
        if path == "/api/next":
            return self._send(200, json.dumps(S.next_record()))
        self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or "{}")
        p = urlparse(self.path).path
        if p == "/api/label":
            S.write_label(body["id"], body["label"])
        elif p == "/api/flag":
            S.write_flag(body["id"], body.get("note", "ambiguous"))
        elif p == "/api/undo":
            S.undo()
        return self._send(200, "{}")


class Store:
    def __init__(self, out: Path, target: int, slice_: str,
                 labels_name="labels_p1.jsonl", only_ids=None):
        self.corpus = out / "corpus_p1.jsonl"
        self.labels = out / labels_name
        self.amb = out / "ambiguous_p1.jsonl"
        self.target = target
        rows = [json.loads(l) for l in self.corpus.read_text().splitlines() if l.strip()]
        if only_ids is not None:
            order = {i: n for n, i in enumerate(only_ids)}
            self.rows = sorted((r for r in rows if r["id"] in order),
                               key=lambda r: order[r["id"]])
        else:
            self.rows = [r for r in rows if slice_ == "all" or r["slice"] == slice_][:target]
        self.by_id = {r["id"]: r for r in self.rows}

    def _load(self, p):
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] \
            if p.exists() else []

    def next_record(self):
        done = {r["id"] for r in self._load(self.labels)}
        flag = {r["id"] for r in self._load(self.amb)}
        todo = [r for r in self.rows if r["id"] not in done and r["id"] not in flag]
        n_done = len(self.rows) - len(todo)
        if not todo:
            return {"done": True, "labelled": len(done), "target": len(self.rows)}
        r = todo[0]
        h = HINTS.get(r["source"], ("&mdash;", "&mdash;", "&mdash;"))
        warn = ""
        if r["source"] in ("Linux", "OpenSSH", "HealthApp", "Proxifier"):
            warn = "This system has <strong>no level position</strong>. A severity word in the message text is prose, not a level (L1, L3)."
        if r["source"] == "Apache":
            warn = "Apache has <strong>no service position</strong> (S3). Leave service empty."
        return {"done": False, "id": r["id"], "source": r["source"], "raw": r["raw"],
                "hint": list(h), "warn": warn, "n": n_done + 1, "target": len(self.rows)}

    def write_label(self, rid, label):
        for f in ("status_code",):
            if label.get(f) is not None:
                try: label[f] = int(label[f])
                except (TypeError, ValueError): pass
        for f in ("latency_ms",):
            if label.get(f) is not None:
                try: label[f] = float(label[f])
                except (TypeError, ValueError): pass
        with self.labels.open("a") as f:
            f.write(json.dumps({**self.by_id[rid], "label": label}) + "\n")

    def write_flag(self, rid, note):
        with self.amb.open("a") as f:
            f.write(json.dumps({**self.by_id[rid], "note": note}) + "\n")

    def undo(self):
        rows = self._load(self.labels)
        if rows:
            with self.labels.open("w") as f:
                for r in rows[:-1]:
                    f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="real-eval")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--target", type=int, default=100)
    ap.add_argument("--slice", default="in-dist", choices=["in-dist", "ood", "all"])
    ap.add_argument("--spotcheck", type=int, default=0,
                    help="blind re-label of N already-labelled lines, into "
                         "spotcheck_p1.jsonl. Existing labels are never read.")
    ap.add_argument("--seed", type=int, default=20260822)
    a = ap.parse_args()

    only = None
    labels_name = "labels_p1.jsonl"
    if a.spotcheck:
        import random
        gold = [json.loads(l)["id"] for l in
                (Path(a.out) / "labels_p1.jsonl").read_text().splitlines() if l.strip()]
        only = sorted(gold)
        random.Random(a.seed).shuffle(only)
        only = only[:a.spotcheck]
        labels_name = "spotcheck_p1.jsonl"
        print(f"BLIND SPOT-CHECK: {len(only)} lines, seed {a.seed}")
        print("  the existing labels are not loaded and are not visible here.\n")
    S = Store(Path(a.out), a.target, a.slice, labels_name, only)
    done = len(S._load(S.labels))
    print(f"P1 labelling UI  ->  http://localhost:{a.port}")
    print(f"  {len(S.rows)} lines in scope ({a.slice}), {done} already labelled")
    print("  ctrl-C to stop; progress is saved after every line\n")
    try:
        HTTPServer(("127.0.0.1", a.port), H).serve_forever()
    except KeyboardInterrupt:
        print("\nstopped. re-run to continue.")
