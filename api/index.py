"""OmniScribe Cloud — a Vercel-deployable serverless edition.

What runs in the cloud (pure Python, no system binaries):
  * Dissect: text or a digital PDF -> guidebook / infographic / flashcards / quiz / mindmap
  * Multi-provider AI extraction (keyless Pollinations by default; Gemini/Groq via env keys)
  * Optional persistence to Supabase (history + asset Storage)

OCR-of-scans and audio transcription need Tesseract/Vosk/ffmpeg and live in the full
desktop app (https://github.com/zed-dz/omniscribe).
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Vercel's filesystem is read-only except /tmp, so point ALL writable dirs there
# (must happen before importing config, which resolves these paths at import time).
_TMP = tempfile.gettempdir()
os.environ.setdefault("OMNISCRIBE_DATA", os.path.join(_TMP, "omniscribe_cloud"))
os.environ.setdefault("OMNISCRIBE_MODELS", os.path.join(_TMP, "omniscribe_models"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse  # noqa: E402

from omniscribe import config, store  # noqa: E402
from omniscribe.dissect import DissectPipeline, extract  # noqa: E402
from omniscribe.dissect import llm as llm_mod  # noqa: E402
from omniscribe.dissect.pipeline import DEFAULT_ASSETS  # noqa: E402

app = FastAPI(title="OmniScribe Cloud", version="1.0.0")
_pipeline = DissectPipeline()
try:
    config.ensure_dirs()
except OSError:
    pass  # read-only FS edge cases; per-request code re-ensures /tmp dirs as needed

GITHUB_URL = "https://github.com/zed-dz/omniscribe"
MIME = {"pdf": "application/pdf", "png": "image/png"}


def _cloud_caps() -> dict:
    providers = llm_mod.available_providers()
    fast = any(p in providers for p in ("gemini", "groq", "openai", "openrouter"))
    return {
        "dissect": True,
        "llm": {"available": bool(providers), "providers": providers,
                "primary": providers[0] if providers else None, "fast": fast},
        "ocr": False,
        "transcribe": False,
        "storage": store.enabled(),
        "github": GITHUB_URL,
    }


def _pdf_to_text(path: str) -> str:
    import pypdf

    reader = pypdf.PdfReader(path)
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


@app.get("/health")
def health():
    return {"status": "ok", "edition": "cloud", "version": "1.0.0"}


@app.get("/api/capabilities")
def capabilities():
    return _cloud_caps()


@app.post("/api/dissect")
async def dissect(
    text: str = Form(""),
    file: UploadFile | None = File(None),
    assets: str = Form(",".join(DEFAULT_ASSETS)),
    use_llm: bool = Form(False),
):
    content = (text or "").strip()
    source_name = "pasted text"

    if file is not None and file.filename:
        suffix = Path(file.filename).suffix.lower()
        raw = await file.read()
        tmp = Path(config.UPLOAD_DIR) / f"{uuid.uuid4().hex[:8]}{suffix}"
        tmp.write_bytes(raw)
        source_name = file.filename
        if suffix == ".pdf":
            try:
                content = _pdf_to_text(str(tmp))
            except Exception as e:
                raise HTTPException(400, f"Could not read PDF: {e}")
            if not content:
                raise HTTPException(
                    422,
                    "This PDF has no embedded text layer (it's scanned/an image). "
                    "Image OCR runs in the full desktop app — see the GitHub link.",
                )
        else:
            content = raw.decode("utf-8", "ignore").strip()

    if not content:
        raise HTTPException(400, "Provide some text or upload a .txt / digital .pdf file.")

    which = [a.strip() for a in assets.split(",") if a.strip()] or DEFAULT_ASSETS
    base = f"omniscribe_{uuid.uuid4().hex[:8]}"
    started = time.time()
    res = _pipeline.process(content, out_dir=config.OUTPUT_DIR, base_name=base,
                            which=which, use_llm=use_llm)

    # Package every asset as base64 (always downloadable) + optional Supabase Storage URL.
    out_assets = {}
    for kind, path in res.files.items():
        p = Path(path)
        ext = p.suffix.lstrip(".")
        data = p.read_bytes()
        public_url = store.upload_asset(str(p), p.name) if store.enabled() else None
        out_assets[kind] = {
            "filename": p.name,
            "ext": ext,
            "mime": MIME.get(ext, "application/octet-stream"),
            "b64": base64.b64encode(data).decode("ascii"),
            "url": public_url,
        }

    schema = res.schema
    if store.enabled():
        store.record_dissection({
            "title": schema.get("title", "")[:200],
            "language": schema.get("language", ""),
            "provider": res.method,
            "input_chars": len(content),
            "assets": {k: v.get("url") or v["filename"] for k, v in out_assets.items()},
        })

    return JSONResponse({
        "source": source_name,
        "method": res.method,
        "seconds": round(time.time() - started, 2),
        "stored": store.enabled(),
        "preview": {
            "title": schema.get("title"),
            "summary": schema.get("summary"),
            "language": schema.get("language"),
            "counts": {
                "concepts": len(schema.get("concepts", [])),
                "flashcards": len(schema.get("flashcards", [])),
                "quiz": len(schema.get("quiz", [])),
                "branches": len(schema.get("mindmap", {}).get("branches", [])),
            },
        },
        "assets": out_assets,
        "llm_error": schema.get("_llm_error"),
    })


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(_HTML)


# --------------------------------------------------------------------------- UI
_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OmniScribe Cloud — Dissect information into study materials</title>
<style>
 :root{--indigo:#4f46e5;--pink:#ec4899;--ink:#1f2937;--muted:#6b7280;--line:#e5e7eb;--bg:#f5f6fa;--card:#fff}
 *{box-sizing:border-box}body{margin:0;font-family:'Segoe UI',Tahoma,system-ui,Arial,sans-serif;background:var(--bg);color:var(--ink)}
 header{background:linear-gradient(120deg,var(--indigo),var(--pink));color:#fff;padding:26px 20px 56px}
 .wrap{max-width:880px;margin:0 auto;padding:0 18px}
 .brand{display:flex;align-items:center;gap:14px}.logo{width:46px;height:46px;border-radius:12px;background:rgba(255,255,255,.18);display:grid;place-items:center;font-size:24px}
 h1{margin:0;font-size:25px}.brand p{margin:3px 0 0;opacity:.92;font-size:13.5px}
 main{max-width:880px;margin:-40px auto 60px;padding:0 18px}
 .card{background:var(--card);border-radius:16px;box-shadow:0 6px 24px rgba(31,41,55,.08);padding:22px;margin-bottom:18px}
 h2{margin:0 0 4px;font-size:19px}.lead{color:var(--muted);font-size:14px;margin:0 0 16px}
 textarea{width:100%;min-height:150px;border:1px solid var(--line);border-radius:10px;padding:12px;font:inherit;resize:vertical}
 .drop{border:2px dashed #c7cbe0;border-radius:12px;padding:16px;text-align:center;color:var(--muted);cursor:pointer;margin-top:12px;background:#fafbff}
 .drop:hover,.drop.drag{border-color:var(--indigo);background:#eef0ff;color:var(--indigo)}.drop .f{color:var(--indigo);font-weight:600;margin-top:6px;word-break:break-all}
 .pills{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
 .pill{display:flex;align-items:center;gap:7px;border:1px solid var(--line);border-radius:20px;padding:7px 13px;font-size:13px;cursor:pointer}
 .pill input{accent-color:var(--indigo)}
 .chk{display:flex;align-items:center;gap:8px;font-size:13.5px;margin:6px 0 16px}
 .btn{background:linear-gradient(120deg,var(--indigo),var(--pink));color:#fff;border:0;border-radius:11px;padding:13px 22px;font-size:15px;font-weight:700;cursor:pointer;box-shadow:0 4px 14px rgba(79,70,229,.3)}
 .btn:disabled{opacity:.55;cursor:not-allowed}
 .banner{border-radius:10px;padding:11px 14px;font-size:13px;margin-bottom:14px}
 .banner.info{background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe}.banner.warn{background:#fff7ed;color:#9a3412;border:1px solid #fed7aa}
 .spin{display:none;margin-top:16px;font-size:14px;color:var(--muted)}.spin.show{display:block}
 .dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--indigo);animation:p 1s infinite alternate;margin-right:6px}@keyframes p{to{opacity:.2}}
 .res{display:none;margin-top:18px}.res.show{display:block}
 .stat-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}.stat{background:#f3f4f6;border-radius:10px;padding:9px 14px;font-size:13px}.stat b{color:#3730a3;font-size:16px;display:block}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
 .acard{border:1px solid var(--line);border-radius:12px;padding:16px;text-align:center;text-decoration:none;color:var(--ink);background:#fff;transition:.15s}
 .acard:hover{border-color:var(--indigo);box-shadow:0 6px 18px rgba(79,70,229,.15);transform:translateY(-2px)}
 .acard .ic{font-size:30px}.acard .nm{font-weight:700;margin-top:8px;font-size:14px}.acard .ty{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
 a{color:var(--indigo)}footer{text-align:center;color:var(--muted);font-size:12.5px;padding:22px}
</style></head><body>
<header><div class="wrap"><div class="brand"><div class="logo">📜</div>
<div><h1>OmniScribe <span style="opacity:.7;font-weight:400">Cloud</span></h1>
<p>Dissect information into study materials — guidebook · infographic · flashcards · quiz · mindmap</p></div></div></div></header>
<main>
 <div class="card">
  <div id="caps"></div>
  <h2>Turn text or a PDF into study materials</h2>
  <p class="lead">Paste text or drop a <b>digital PDF</b> / <b>.txt</b>. Need OCR of scans or audio transcription? That's in the <a href="" id="ghlink" target="_blank">full desktop app</a>.</p>
  <textarea id="text" placeholder="Paste a transcript, article, lecture notes, or any text…"></textarea>
  <div class="drop" id="drop">…or drop a <b>.pdf</b> / <b>.txt</b> file<div class="f" id="fname"></div>
   <input type="file" id="file" accept=".txt,.md,.pdf" hidden></div>
  <p class="lead" style="margin:16px 0 6px">Assets</p>
  <div class="pills" id="assets"></div>
  <label class="chk"><input type="checkbox" id="ai"> Use AI extraction <span style="color:var(--muted)">(richer; off = instant offline)</span></label>
  <button class="btn" id="go">Generate study materials</button>
  <div class="spin" id="spin"><span class="dot"></span><span id="spinmsg">Generating…</span></div>
  <div class="res" id="res"></div>
 </div>
</main>
<footer>OmniScribe Cloud · <a href="" id="ghfoot" target="_blank">source on GitHub</a> · OCR &amp; speech in the desktop app</footer>
<script>
const $=s=>document.querySelector(s);
const ICON={guidebook:"📘",infographic:"📊",flashcards:"🎴",quiz:"❓",mindmap:"🧠"};
let CAPS=null,FILE=null;
async function boot(){
 CAPS=await (await fetch("/api/capabilities")).json();
 $("#ghlink").href=CAPS.github;$("#ghfoot").href=CAPS.github;
 const ap=$("#assets");["guidebook","infographic","flashcards","quiz","mindmap"].forEach(a=>{
   const l=document.createElement("label");l.className="pill";
   l.innerHTML=`<input type="checkbox" value="${a}" checked> ${ICON[a]} ${a}`;ap.appendChild(l);});
 const c=$("#caps");
 if(CAPS.llm.available){
   const note=CAPS.llm.fast?`fast provider <b>${CAPS.llm.primary}</b>`:`free keyless <b>${CAPS.llm.primary}</b> (~20-40s; add a GEMINI_API_KEY for speed)`;
   c.innerHTML=`<div class="banner info">AI extraction available via ${note}. ${CAPS.storage?"Results are saved to your database. ":""}</div>`;
   $("#ai").checked=CAPS.llm.fast;
 } else c.innerHTML=`<div class="banner warn">Offline engine only — still produces all assets instantly.</div>`;
}
$("#drop").onclick=()=>$("#file").click();
$("#drop").addEventListener("dragover",e=>{e.preventDefault();$("#drop").classList.add("drag")});
$("#drop").addEventListener("dragleave",()=>$("#drop").classList.remove("drag"));
$("#drop").addEventListener("drop",e=>{e.preventDefault();$("#drop").classList.remove("drag");if(e.dataTransfer.files[0]){$("#file").files=e.dataTransfer.files;pick()}});
$("#file").addEventListener("change",pick);
function pick(){FILE=$("#file").files[0];$("#fname").textContent=FILE?("📎 "+FILE.name):""}
$("#go").onclick=async()=>{
 const text=$("#text").value.trim();
 if(!text&&!FILE){alert("Paste text or drop a file first.");return;}
 const fd=new FormData();
 if(FILE)fd.append("file",FILE);else fd.append("text",text);
 fd.append("assets",[...document.querySelectorAll("#assets input:checked")].map(i=>i.value).join(","));
 fd.append("use_llm",$("#ai").checked);
 $("#go").disabled=true;$("#res").className="res";
 $("#spin").className="spin show";$("#spinmsg").textContent=$("#ai").checked?"Generating with AI (may take ~20-40s)…":"Generating…";
 try{
   const r=await fetch("/api/dissect",{method:"POST",body:fd});
   if(!r.ok){const t=await r.json().catch(()=>({detail:r.statusText}));throw new Error(t.detail||"failed");}
   render(await r.json());
 }catch(e){$("#res").innerHTML=`<div class="banner warn">${esc(e.message)}</div>`;$("#res").className="res show";}
 finally{$("#go").disabled=false;$("#spin").className="spin";}
};
function render(d){
 const p=d.preview||{},c=p.counts||{};
 const isAI=d.method&&!d.method.startsWith("heuristic");
 let html=`<div class="banner info">Generated via <b>${isAI?("AI · "+d.method):"offline engine"}</b> in ${d.seconds}s${d.stored?" · saved to database":""}. ${p.title?("— "+esc(p.title)):""}</div>`;
 if(d.llm_error)html+=`<div class="banner warn">AI note: ${esc(d.llm_error)}</div>`;
 html+=`<div class="stat-row"><div class="stat"><b>${c.concepts||0}</b>concepts</div><div class="stat"><b>${c.flashcards||0}</b>flashcards</div><div class="stat"><b>${c.quiz||0}</b>quiz</div><div class="stat"><b>${c.branches||0}</b>branches</div></div>`;
 html+=`<div class="grid">`+Object.entries(d.assets).map(([k,a])=>{
   const href=a.url||("data:"+a.mime+";base64,"+a.b64);
   return `<a class="acard" href="${href}" download="${a.filename}" target="_blank"><div class="ic">${ICON[k]||"📄"}</div><div class="nm">${k}</div><div class="ty">${a.ext}</div></a>`;
 }).join("")+`</div>`;
 $("#res").innerHTML=html;$("#res").className="res show";
}
function esc(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}
boot();
</script></body></html>"""
