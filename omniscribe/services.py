"""High-level service functions shared by the web API and the CLI.

Each ``run_*`` returns a JSON-serialisable dict and writes downloadable artifacts into
``config.OUTPUT_DIR``. A ``progress(fraction, message)`` callback is threaded through so
callers (web jobs / CLI) can show live progress.
"""
from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Callable

from . import config, export
from .dissect import DissectPipeline
from .dissect.pipeline import DEFAULT_ASSETS
from .ocr import OCRPipeline
from .ocr import postprocess
from .transcribe import TranscribePipeline
from .transcribe import pipeline as tpipe

Progress = Callable[[float, str], None]


def _noop(_p: float, _m: str = "") -> None:
    pass


def _slug(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("_")
    return stem[:60] or "output"


def _stamp() -> str:
    # Timestamp + short random token so concurrent jobs on the same file never collide.
    return time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]


# --------------------------------------------------------------------------- shared
_ocr_pipeline: OCRPipeline | None = None
_dissect_pipeline = DissectPipeline()
_stt_pipelines: dict[str, TranscribePipeline] = {}


def ocr_pipeline() -> OCRPipeline:
    global _ocr_pipeline
    if _ocr_pipeline is None:
        _ocr_pipeline = OCRPipeline()
    return _ocr_pipeline


def stt_pipeline(lang: str) -> TranscribePipeline:
    if lang not in _stt_pipelines:
        _stt_pipelines[lang] = TranscribePipeline(lang=lang)
    return _stt_pipelines[lang]


# --------------------------------------------------------------------------- OCR
def run_ocr(
    path: str,
    *,
    lang: str = config.DEFAULT_OCR_LANG,
    preset: str = config.DEFAULT_OCR_PRESET,
    page_range: tuple[int, int] | None = None,
    prefer_embedded: bool = True,
    deskew: bool = False,
    denoise: bool = False,
    remove_diacritics: bool = False,
    normalize_numbers: bool = False,
    formats: set[str] | None = None,
    progress: Progress = _noop,
) -> dict:
    res = ocr_pipeline().process(
        path, lang=lang, preset=preset, page_range=page_range,
        prefer_embedded=prefer_embedded, deskew=deskew, denoise=denoise,
        remove_diacritics=remove_diacritics, normalize_numbers=normalize_numbers,
        progress=lambda done, total, msg: progress(done / max(1, total), msg),
    )
    base = f"{_slug(path)}_ocr_{_stamp()}"
    records = [{"label": f"Page {p.page}", "text": p.text} for p in res.pages]
    files = export.export_all(
        records, res.text, config.OUTPUT_DIR, base,
        formats=formats or {"txt", "json", "md", "html", "csv"},
        title=f"OCR — {Path(path).name}",
        extra_json={"lang": lang, "preset": preset, "engine": res.engine},
    )
    return {
        "text": res.text,
        "pages": [{"page": p.page, "source": p.source, "chars": p.char_count} for p in res.pages],
        "page_count": res.page_count,
        "stats": postprocess.stats(res.text),
        "seconds": res.seconds,
        "engine": res.engine,
        "lang": lang,
        "preset": preset,
        "files": {k: Path(v).name for k, v in files.items()},
    }


# --------------------------------------------------------------------------- transcribe
def run_transcribe(
    path: str,
    *,
    lang: str = config.DEFAULT_STT_LANG,
    progress: Progress = _noop,
) -> dict:
    pipe = stt_pipeline(lang)
    tr = pipe.process(path, progress=progress)

    base = f"{_slug(path)}_transcript_{_stamp()}"
    config.ensure_dirs()
    out = config.OUTPUT_DIR
    files: dict[str, str] = {}
    files["txt"] = export.export_text(tr.text, out / f"{base}.txt")
    files["srt"] = export.export_text(tpipe.to_srt(tr.segments), out / f"{base}.srt")
    files["vtt"] = export.export_text(tpipe.to_vtt(tr.segments), out / f"{base}.vtt")
    files["json"] = export.export_json(tr.to_dict(), out / f"{base}.json")

    return {
        "text": tr.text,
        "segments": [s.__dict__ for s in tr.segments],
        "duration": tr.duration,
        "seconds": tr.seconds,
        "word_count": len(tr.text.split()),
        "lang": lang,
        "engine": tr.engine,
        "files": {k: Path(v).name for k, v in files.items()},
    }


# --------------------------------------------------------------------------- dissect
def run_dissect(
    text: str,
    *,
    which: list[str] | None = None,
    use_llm: bool = True,
    model: str | None = None,
    base_hint: str = "study_materials",
    progress: Progress = _noop,
) -> dict:
    progress(0.1, "Analysing content")
    which = which or DEFAULT_ASSETS
    base = f"{_slug(base_hint)}_{_stamp()}"
    res = _dissect_pipeline.process(
        text, base_name=base, which=which, use_llm=use_llm, model=model,
    )
    progress(1.0, "Assets ready")
    schema = res.schema
    preview = {
        "title": schema.get("title"),
        "summary": schema.get("summary"),
        "language": schema.get("language"),
        "counts": {
            "concepts": len(schema.get("concepts", [])),
            "flashcards": len(schema.get("flashcards", [])),
            "quiz": len(schema.get("quiz", [])),
            "mindmap_branches": len(schema.get("mindmap", {}).get("branches", [])),
        },
    }
    return {
        "method": res.method,
        "preview": preview,
        "schema": schema,
        "seconds": res.seconds,
        "files": {k: Path(v).name for k, v in res.files.items()},
        "llm_error": schema.get("_llm_error"),
    }


# --------------------------------------------------------------------------- pipeline
def detect_kind(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in config.PDF_EXTENSIONS or ext in config.IMAGE_EXTENSIONS:
        return "ocr"
    if ext in config.AUDIO_EXTENSIONS:
        return "audio"
    raise ValueError(f"Unsupported file type: {ext}")


def run_pipeline(
    path: str,
    *,
    ocr_lang: str = config.DEFAULT_OCR_LANG,
    ocr_preset: str = config.DEFAULT_OCR_PRESET,
    stt_lang: str = config.DEFAULT_STT_LANG,
    which: list[str] | None = None,
    use_llm: bool = True,
    model: str | None = None,
    progress: Progress = _noop,
) -> dict:
    """Full chain: extract text from a document/audio, then dissect it into study assets."""
    kind = detect_kind(path)
    if kind == "ocr":
        progress(0.05, "Reading document (OCR)")
        stage = run_ocr(
            path, lang=ocr_lang, preset=ocr_preset,
            progress=lambda f, m: progress(0.05 + 0.5 * f, m),
        )
        text = stage["text"]
    else:
        progress(0.05, "Transcribing audio")
        stage = run_transcribe(
            path, lang=stt_lang,
            progress=lambda f, m: progress(0.05 + 0.5 * f, m),
        )
        text = stage["text"]

    if not text.strip():
        return {"stage_kind": kind, "stage": stage, "dissect": None,
                "warning": "No text was extracted, so no study materials were generated."}

    progress(0.6, "Creating study materials")
    dissect = run_dissect(
        text, which=which, use_llm=use_llm, model=model,
        base_hint=Path(path).stem,
        progress=lambda f, m: progress(0.6 + 0.4 * f, m),
    )
    return {"stage_kind": kind, "stage": stage, "dissect": dissect}
