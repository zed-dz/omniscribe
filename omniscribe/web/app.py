"""FastAPI application exposing OmniScribe's three engines + the chained pipeline."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import capabilities, config, services
from ..transcribe import model_manager
from .jobs import manager

config.ensure_dirs()
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="OmniScribe", version="1.0.0", description="Reads. Listens. Teaches.")


# --------------------------------------------------------------------------- helpers
def _save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "file").suffix
    dest = config.UPLOAD_DIR / f"{uuid.uuid4().hex[:10]}{suffix}"
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
    finally:
        upload.file.close()
    return dest


def _csv_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    return items or None


def _parse_range(value: str | None) -> tuple[int, int] | None:
    if not value or not value.strip():
        return None
    txt = value.strip()
    try:
        if "-" in txt:
            a, b = txt.split("-", 1)
            start, end = int(a) - 1, int(b)  # 1-indexed inclusive -> 0-indexed exclusive
        else:
            n = int(txt)
            start, end = n - 1, n
    except ValueError:
        raise HTTPException(400, f"Invalid page range '{value}' (use e.g. '1-5' or '3')")
    if start < 0 or end <= start:
        raise HTTPException(400, f"Invalid page range '{value}'")
    return (start, end)


# --------------------------------------------------------------------------- meta
@app.get("/api/capabilities")
def api_capabilities():
    return capabilities.snapshot()


@app.get("/api/config")
def api_config():
    return {
        "ocr_languages": config.OCR_LANGUAGES,
        "ocr_presets": {k: v for k, v in config.OCR_PRESETS.items()},
        "default_ocr_lang": config.DEFAULT_OCR_LANG,
        "default_ocr_preset": config.DEFAULT_OCR_PRESET,
        "stt_models": {
            lang: {**spec, "installed": model_manager.is_installed(lang)}
            for lang, spec in config.VOSK_MODELS.items()
        },
        "default_stt_lang": config.DEFAULT_STT_LANG,
        "assets": ["guidebook", "infographic", "flashcards", "quiz", "mindmap"],
        "image_exts": sorted(config.IMAGE_EXTENSIONS),
        "pdf_exts": sorted(config.PDF_EXTENSIONS),
        "audio_exts": sorted(config.AUDIO_EXTENSIONS),
        "version": "1.0.0",
    }


@app.get("/api/job/{job_id}")
def api_job(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.public()


# --------------------------------------------------------------------------- OCR
@app.post("/api/ocr")
async def api_ocr(
    file: UploadFile = File(...),
    lang: str = Form(config.DEFAULT_OCR_LANG),
    preset: str = Form(config.DEFAULT_OCR_PRESET),
    page_range: str = Form(""),
    prefer_embedded: bool = Form(True),
    deskew: bool = Form(False),
    denoise: bool = Form(False),
    remove_diacritics: bool = Form(False),
    normalize_numbers: bool = Form(False),
    formats: str = Form("txt,json,md,html,csv"),
):
    if not capabilities.snapshot()["ocr"]["available"]:
        raise HTTPException(503, "OCR engine unavailable (check Tesseract/PyMuPDF)")
    path = _save_upload(file)
    pr = _parse_range(page_range)
    fmts = set(_csv_list(formats) or [])

    def work(progress):
        return services.run_ocr(
            str(path), lang=lang, preset=preset, page_range=pr,
            prefer_embedded=prefer_embedded, deskew=deskew, denoise=denoise,
            remove_diacritics=remove_diacritics, normalize_numbers=normalize_numbers,
            formats=fmts, progress=progress,
        )

    job = manager.submit("ocr", work)
    return {"job_id": job.id}


# --------------------------------------------------------------------------- transcribe
@app.post("/api/transcribe")
async def api_transcribe(
    file: UploadFile = File(...),
    lang: str = Form(config.DEFAULT_STT_LANG),
):
    cap = capabilities.snapshot()["transcribe"]
    if not cap["available"]:
        raise HTTPException(503, "Transcription engine unavailable (check Vosk/ffmpeg)")
    path = _save_upload(file)

    def work(progress):
        if not model_manager.is_installed(lang):
            progress(0.0, "Downloading speech model (first run)")
        return services.run_transcribe(str(path), lang=lang, progress=progress)

    job = manager.submit("transcribe", work)
    return {"job_id": job.id}


# --------------------------------------------------------------------------- dissect
@app.post("/api/dissect")
async def api_dissect(
    text: str = Form(""),
    file: UploadFile | None = File(None),
    assets: str = Form("guidebook,infographic,flashcards,quiz,mindmap"),
    use_llm: bool = Form(True),
):
    content = text or ""
    if file is not None:
        path = _save_upload(file)
        content = path.read_text(encoding="utf-8", errors="ignore")
    if not content.strip():
        raise HTTPException(400, "Provide text or a text file to dissect")
    which = _csv_list(assets)

    def work(progress):
        return services.run_dissect(content, which=which, use_llm=use_llm, progress=progress)

    job = manager.submit("dissect", work)
    return {"job_id": job.id}


# --------------------------------------------------------------------------- pipeline
@app.post("/api/pipeline")
async def api_pipeline(
    file: UploadFile = File(...),
    ocr_lang: str = Form(config.DEFAULT_OCR_LANG),
    ocr_preset: str = Form(config.DEFAULT_OCR_PRESET),
    stt_lang: str = Form(config.DEFAULT_STT_LANG),
    assets: str = Form("guidebook,infographic,flashcards,quiz,mindmap"),
    use_llm: bool = Form(True),
):
    path = _save_upload(file)
    which = _csv_list(assets)

    def work(progress):
        return services.run_pipeline(
            str(path), ocr_lang=ocr_lang, ocr_preset=ocr_preset, stt_lang=stt_lang,
            which=which, use_llm=use_llm, progress=progress,
        )

    job = manager.submit("pipeline", work)
    return {"job_id": job.id}


# --------------------------------------------------------------------------- models
@app.get("/api/models")
def api_models():
    return {
        lang: {**spec, "installed": model_manager.is_installed(lang)}
        for lang, spec in config.VOSK_MODELS.items()
    }


@app.post("/api/models/download")
async def api_models_download(lang: str = Form(...)):
    if lang not in config.VOSK_MODELS:
        raise HTTPException(400, f"Unknown model language: {lang}")

    def work(progress):
        model_manager.download_model(lang, progress=lambda msg, pct: progress(pct / 100.0, msg))
        return {"lang": lang, "installed": True}

    job = manager.submit("model-download", work)
    return {"job_id": job.id}


# --------------------------------------------------------------------------- downloads
@app.get("/download/{name}")
def download(name: str):
    # Prevent path traversal: only serve plain file names from the outputs dir.
    safe = Path(name).name
    target = config.OUTPUT_DIR / safe
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(str(target), filename=safe)


# --------------------------------------------------------------------------- UI
@app.get("/", response_class=HTMLResponse)
def index():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return HTMLResponse(idx.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>OmniScribe</h1><p>UI not found.</p>")


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
