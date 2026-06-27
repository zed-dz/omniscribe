# OmniScribe — Master Prompt

> The single prompt/spec that fuses the four source folders into one world-class tool.
> Hand this to an autonomous coding agent and it will (re)build OmniScribe.

---

## Mission

Combine four sibling folders into **one** fast, reliable, feature-rich, locally-running
tool with a UI:

| Source folder | Capability to absorb |
|---|---|
| **Arabic OCR** | EasyOCR pipeline, Arabic pre/post-processing, presets, multi-format export, GUI ideas |
| **Project OCR** | Multi-engine OCR experiments — keep the **Tesseract** path (proven), drop the failed Surya/pdftotext paths |
| **Text to speech (ogg)** | *Actually speech-to-text* — Vosk (offline, light), Whisper (accurate), Google (cloud). Keep an offline engine |
| **Tool to disect information** | Transcript → educational assets (guidebook/infographic/flashcards/mindmap) via ReportLab/PIL, LLM-driven |

Result: **OmniScribe — "Reads. Listens. Teaches."**
- **Reads** = OCR, **Listens** = transcription, **Teaches** = study-material generation,
- plus a **Pipeline** that chains document/audio → text → study materials.

## Hard requirements
1. **Reliability first** — no crashes. Every engine is optional and detected at runtime;
   missing dependencies degrade gracefully and are reported, never fatal.
2. **Fast & light** — CPU-only; no GPU/PyTorch. Must install & run on Python 3.14, 4 cores, 8 GB RAM.
3. **Feature-rich** — multi-language OCR (Arabic/English/French), digital-vs-scanned auto-routing,
   timestamps + subtitles, five study-asset types, multi-format export.
4. **A real UI** — modern web app (no build step, no CDN) with drag-drop, live progress, downloads.
5. **Verified end-to-end** — automated tests with *real* inputs (real Arabic PDF, synthesised
   speech, generated PDFs/PNGs) and the full web stack. Everything must actually work.

## Architecture to produce
- `omniscribe/config.py` — paths, presets, language maps, font + tool detection.
- `omniscribe/capabilities.py` — detect Tesseract, PyMuPDF, ffmpeg, Vosk, Anthropic; report status.
- `omniscribe/ocr/` — `pdf.py` (PyMuPDF render + embedded text), `preprocess.py` (grayscale,
  autocontrast, sharpen, deskew, denoise, Otsu), `engine.py` (Tesseract, pluggable),
  `postprocess.py` (NFKC + Arabic normalisation), `pipeline.py` (auto digital/scanned per page).
- `omniscribe/transcribe/` — `audio.py` (any format → 16 kHz mono WAV via imageio-ffmpeg),
  `model_manager.py` (download/locate Vosk models), `engine.py` (Vosk + word timestamps),
  `pipeline.py` (segment grouping, SRT/VTT).
- `omniscribe/dissect/` — `extract.py` (Anthropic LLM **and** a heuristic fallback producing the
  *same* schema), `assets.py` (ReportLab/PIL generators with Arabic shaping via
  arabic-reshaper + python-bidi), `pipeline.py`.
- `omniscribe/export.py` — TXT/JSON/CSV/Markdown/HTML (RTL-aware).
- `omniscribe/services.py` — `run_ocr / run_transcribe / run_dissect / run_pipeline`, shared by web + CLI.
- `omniscribe/web/` — FastAPI `app.py` + background-job `jobs.py` + `static/index.html` SPA.
- `run.py` (launcher), `cli.py` (unified CLI), `tests/` (pytest), `requirements.txt`, `README.md`.

## Engine choices (grounded in what installs on Python 3.14, CPU-only)
- **OCR:** Tesseract via `pytesseract`; render PDFs with **PyMuPDF**; use a PDF's embedded text
  layer when present (instant), OCR only scanned pages.
- **Transcribe:** **Vosk** (offline, ~40 MB models, auto-download on first use); convert audio
  with the **imageio-ffmpeg** bundled binary (no system ffmpeg).
- **Dissect:** **Anthropic** (`claude-sonnet-4-6`) when a key + credits exist; otherwise a
  heuristic extractor. Render assets with **ReportLab** (PDF) + **Pillow** (PNG). Arabic must be
  shaped + bidi-reordered per line (ReportLab/PIL don't do complex scripts).

## Build method (loop until done)
1. Probe the environment; confirm each dependency installs **and imports** before relying on it.
2. Build each module, smoke-test immediately with a real input.
3. Write a pytest suite using real artifacts: synthetic English image + real Arabic PDF for OCR;
   **Windows SAPI**-synthesised speech for transcription; validate generated PDFs/PNGs by header;
   exercise the FastAPI stack with `TestClient`.
4. Run the suite; fix in a loop until green.
5. Launch the live server; verify every endpoint over HTTP and both pipeline branches.
6. Adversarial code review; fix real bugs (e.g. quiz option overflow, page-range validation,
   filename collisions, file-handle leaks). Re-test.

## Definition of done
All engines READY, web UI renders, CLI works, the full pipeline runs for both a scanned PDF and
an audio file, Arabic renders correctly in PDFs/PNGs, and the whole test suite passes.
