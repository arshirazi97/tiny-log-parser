#!/usr/bin/env python3
"""Review pass over labels_p1.jsonl in the browser.

    python3 real-eval/review_ui.py     ->  http://localhost:8766

Shows every labelled line with its raw log line and the label side by side.
Edit any field and hit Save row; the record is rewritten, the touched fields
are re-stamped `hand-corrected` in `label_source`, and the record is marked
reviewed. Approve leaves the values alone and marks it reviewed.

This is a REVIEW, which is weaker evidence than independent labelling: seeing a
proposed value anchors the reviewer to it. It is recorded as a review and not
described as hand-labelling. The blind 25-line subset in spotcheck_ui.py is the
part that carries independent weight.
"""
import argparse, json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

F3 = ["timestamp", "level", "service"]
FX = ["trace_id", "status_code", "latency_ms"]

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>P1 review</title><style>
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#12141a;color:#e6e8ee}
.wrap{max-width:1180px;margin:0 auto;padding:20px 20px 60px}
h1{font-size:15px;margin:0 0 4px}
.sub{color:#79808f;font-size:13px;margin-bottom:16px}
.stat{position:sticky;top:0;background:#12141a;padding:10px 0 12px;border-bottom:1px solid #232734;
      margin-bottom:16px;z-index:5;font-size:13px;color:#9aa2b1;display:flex;gap:18px;align-items:center}
.stat b{color:#e6e8ee}
.f{display:inline-block;padding:3px 9px;border-radius:99px;background:#26304a;color:#9fc0ff;font-size:12px}
.row{border:1px solid #232734;border-radius:8px;margin-bottom:12px;overflow:hidden;background:#161922}
.row.ok{border-color:#2b4a35}
.row.edited{border-color:#5b8cff}
.hd{display:flex;gap:10px;align-items:center;padding:9px 13px;background:#1a1e29;font-size:12px;color:#8b93a4}
.hd .n{font-variant-numeric:tabular-nums;color:#5f6675}
.hd .src{padding:2px 8px;border-radius:99px;background:#26304a;color:#9fc0ff}
.hd .st{margin-left:auto}
.raw{padding:11px 13px;font:12.5px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace;
     color:#c8cfdd;background:#0b0d12;word-break:break-all;border-bottom:1px solid #1f2430}
.flds{display:grid;grid-template-columns:auto 1fr;gap:7px 12px;padding:11px 13px;align-items:center}
.k{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#79808f;text-align:right;font-weight:600}
input{width:100%;background:#0b0d12;border:1px solid #2b3040;border-radius:5px;color:#e6e8ee;
      padding:6px 9px;font:13px ui-monospace,Menlo,monospace}
input:focus{outline:none;border-color:#5b8cff}
input.null{color:#5f6675;font-style:italic}
.act{padding:9px 13px;display:flex;gap:8px;border-top:1px solid #1f2430}
button{border-radius:5px;padding:6px 14px;font-size:12.5px;cursor:pointer;font-family:inherit;border:1px solid #2b3040;
       background:#1a1e29;color:#c3c9d6}
button.ok{background:#2b4a35;border-color:#2b4a35;color:#c8f0d4}
button.sv{background:#5b8cff;border-color:#5b8cff;color:#0b0d12;font-weight:600}
.hint{color:#5f6675;font-size:12px;align-self:center;margin-left:auto}
</style></head><body><div class=wrap>
<h1>P1 label review</h1>
<div class=sub>Every field editable. <b>Approve</b> keeps the values; <b>Save row</b> records your edits and
re-stamps the changed fields as hand-corrected. Empty box = null.</div>
<div class=stat id=stat></div><div id=list></div></div>
<script>
let D=[];
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const F3=['timestamp','level','service'], FX=['trace_id','status_code','latency_ms'];

function stat(){
  const rev=D.filter(r=>r.reviewed).length, cor=D.filter(r=>r.corrected).length;
  document.getElementById('stat').innerHTML=
    `<span>reviewed <b>${rev}</b> / ${D.length}</span><span>corrected <b>${cor}</b></span>`+
    `<span style="margin-left:auto;color:#5f6675">agreement so far: <b>${rev?((rev-cor)/rev*100).toFixed(0):'—'}%</b></span>`;
}
function render(){
  document.getElementById('list').innerHTML=D.map((r,i)=>{
    const fld=f=>`<div class=k>${f}</div><div><input id="${f}_${r.id}" value="${esc(r.label[f])}"
        class="${r.label[f]==null?'null':''}" placeholder="null" spellcheck=false></div>`;
    const extras=FX.some(f=>r.label[f]!=null)?FX.map(fld).join(''):'';
    return `<div class="row ${r.reviewed?(r.corrected?'edited':'ok'):''}" id="row_${r.id}">
      <div class=hd><span class=n>${i+1}</span><span class=src>${r.source}</span>
        <span class=st>${r.reviewed?(r.corrected?'corrected':'approved'):'unreviewed'}</span></div>
      <div class=raw>${esc(r.raw)}</div>
      <div class=flds>${F3.map(fld).join('')}${extras}</div>
      <div class=act>
        <button class=ok onclick="mark('${r.id}',false)">Approve</button>
        <button class=sv onclick="mark('${r.id}',true)">Save row</button>
        <span class=hint>${esc(r.msg||'').slice(0,90)}</span>
      </div></div>`;}).join('');
  stat();
}
async function mark(id,save){
  const r=D.find(x=>x.id===id);
  let lab={};
  [...F3,...FX].forEach(f=>{const e=document.getElementById(f+'_'+id);
    if(!e){lab[f]=r.label[f];return;}
    const v=e.value.trim();
    lab[f]=(v===''||v.toLowerCase()==='null'||v.toLowerCase()==='none')?null:v;});
  const res=await fetch('/api/update',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:id,label:save?lab:r.label})});
  const j=await res.json();
  Object.assign(r,j); render();
  document.getElementById('row_'+id).scrollIntoView({block:'nearest'});
}
fetch('/api/all').then(r=>r.json()).then(d=>{D=d;render();});
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _s(self, code, body, ct="application/json"):
        b = body.encode(); self.send_response(code)
        self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if urlparse(self.path).path == "/":
            return self._s(200, PAGE, "text/html; charset=utf-8")
        if urlparse(self.path).path == "/api/all":
            return self._s(200, json.dumps([
                {"id": r["id"], "source": r["source"], "raw": r["raw"], "label": r["label"],
                 "reviewed": r.get("reviewed", False), "corrected": r.get("corrected", False),
                 "msg": (r["label"].get("message") or "")} for r in S.rows]))
        self._s(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or "{}")
        return self._s(200, json.dumps(S.update(body["id"], body["label"])))


class Store:
    def __init__(self, p: Path):
        self.p = p
        self.rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]

    def update(self, rid, new):
        for r in self.rows:
            if r["id"] != rid:
                continue
            changed = [f for f in F3 + FX
                       if str(r["label"].get(f)) != str(new.get(f, r["label"].get(f)))]
            for f in F3 + FX:
                if f in new:
                    v = new[f]
                    if f == "status_code" and v is not None:
                        try: v = int(v)
                        except (TypeError, ValueError): pass
                    if f == "latency_ms" and v is not None:
                        try: v = float(v)
                        except (TypeError, ValueError): pass
                    r["label"][f] = v
            src = r.setdefault("label_source", {})
            for f in changed:
                src[f] = "hand-corrected"
            r["reviewed"] = True
            r["corrected"] = bool(changed) or r.get("corrected", False)
            self.flush()
            return {"label": r["label"], "reviewed": True, "corrected": r["corrected"]}
        return {}

    def flush(self):
        with self.p.open("w") as f:
            for r in self.rows:
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="real-eval/labels_p1.jsonl")
    ap.add_argument("--port", type=int, default=8766)
    a = ap.parse_args()
    S = Store(Path(a.labels))
    print(f"P1 review UI  ->  http://localhost:{a.port}")
    print(f"  {len(S.rows)} labelled records; edits save immediately\n")
    try:
        HTTPServer(("127.0.0.1", a.port), H).serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
