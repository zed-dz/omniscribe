# OmniScribe

**Turn a scan, a PDF or a voice note into text, flashcards, a quiz and a summary.**

**[Try it in your browser](https://omniscribe-cloud.vercel.app)**. Paste text or add a digital PDF. Scans and audio need the full app on your PC, below.

## Who it is for

- Students with scanned pages and recorded lessons.
- Teachers who want a quiz and flashcards from their own notes.
- Anyone who works in Arabic, English or French.

## What it does

| Part | What you give it | What you get |
|---|---|---|
| **OCR** | PDF or image in Arabic, English or French | Text, as TXT, JSON, CSV, Markdown or HTML |
| **Transcribe** | Speech audio | Text with times, and SRT or VTT subtitles |
| **Dissect** | Any text | Guidebook, infographic, flashcards, quiz, mind map |
| **Pipeline** | A scan or a voice note | All of the above in one go |

It has a web page and a command line. No GPU needed.

## Privacy

- OCR and speech run on your PC. A speech model is downloaded the first time.
- **Dissect with AI sends your text out.** With no key it uses Pollinations, a free online service. To stay offline, untick **Use AI**, pass `--no-llm`, or set `OMNISCRIBE_POLLINATIONS=0`.
- The hosted demo runs on Vercel. Do not paste private text there.

---

## Quick start (full local app — OCR + speech + study materials)

```bash
git clone https://github.com/zed-dz/omniscribe
cd omniscribe
pip install -r requirements-full.txt     # full deps (Tesseract must be installed separately)
python run.py                            # launches the web app and opens your browser
```

Then open <http://127.0.0.1:8000> (opens automatically).

### External requirement
- **Tesseract OCR 5.x** with the `ara`, `eng`, `fra` language packs.
  Windows installer: <https://github.com/UB-Mannheim/tesseract/wiki>
  (ffmpeg is bundled automatically via the `imageio-ffmpeg` wheel — nothing to install.)

The first transcription downloads a small (~40 MB) Vosk speech model automatically.

---

## Web UI

Four tabs, drag-and-drop everywhere, live progress bars, one-click downloads:

- **OCR** — drop a PDF/image, pick language & quality, get text + TXT/JSON/CSV/MD/HTML exports.
- **Transcribe** — drop audio, get a transcript + **SRT/VTT** subtitles with timestamps.
- **Dissect** — paste text (or drop a `.txt`), pick which assets to generate.
- **Pipeline** — drop *anything* (document **or** audio) and get study materials end-to-end.

The header shows a live capability panel (which engines are ready).

---

## Command line

```bash
python cli.py caps                                   # show engine status
python cli.py ocr book.pdf --lang ara --preset balanced --pages 1-10
python cli.py transcribe voice.ogg --lang en
python cli.py dissect notes.txt --assets guidebook,flashcards,mindmap
python cli.py pipeline scan.pdf                      # OCR/transcribe -> study materials
python cli.py models list                            # speech models
python cli.py models download ar                     # add Arabic speech model
python cli.py serve --port 8000                      # run the web UI
```

All artifacts are written to `data/outputs/`.

---

## How it works (architecture)

```
omniscribe/
  config.py          paths, presets, language maps, font detection
  capabilities.py    runtime detection of every engine (graceful degradation)
  services.py        high-level run_ocr / run_transcribe / run_dissect / run_pipeline
  export.py          TXT / JSON / CSV / Markdown / HTML (RTL-aware) writers
  ocr/
    pdf.py           PyMuPDF: render pages + read embedded text layers
    preprocess.py    grayscale, autocontrast, sharpen, deskew, denoise, Otsu
    engine.py        Tesseract backend (pluggable interface)
    postprocess.py   NFKC + Arabic normalisation, stats, word frequency
    pipeline.py      auto digital-vs-scanned routing per page
  transcribe/
    audio.py         any format -> 16 kHz mono WAV (bundled ffmpeg)
    model_manager.py download/locate Vosk models on demand
    engine.py        Vosk recognition with word timestamps
    pipeline.py      grouping into subtitle segments, SRT/VTT
  dissect/
    extract.py       Anthropic LLM extraction + full heuristic fallback (same schema)
    assets.py        ReportLab + PIL generators, Arabic shaping (reshaper+bidi)
    pipeline.py      schema -> asset files
  web/
    app.py           FastAPI endpoints + background-job manager
    jobs.py          in-memory job queue with live progress
    static/index.html  the single-page UI (no build step, no CDN)
run.py               launcher (server + browser)
cli.py               unified command line
tests/               38 tests incl. real OCR, real speech, full web stack
```

### Design principles
- **Reliability first.** Every engine is optional and detected at runtime; a missing
  dependency degrades gracefully instead of crashing. Dissect always works (offline
  heuristic) even with no AI key.
- **Fast & light.** Tesseract + Vosk + PyMuPDF — CPU-only, no PyTorch, no GPU.
- **Arabic done right.** RTL detection, contextual letter shaping and bidi reordering in
  both PDFs and PNGs; digital Arabic PDFs use their text layer instantly.

---

## AI extraction — multi-provider, works with **no key**

`Dissect` extracts its structure through a resilient **provider chain** (`omniscribe/dissect/llm.py`).
It tries each configured provider in order and falls back automatically:

| Order | Provider | How to enable | Notes |
|---|---|---|---|
| 1 | **Gemini** | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | free tier, high quality |
| 2 | **Anthropic** | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| 3 | **Groq** | `GROQ_API_KEY` | OpenAI-compatible, very fast |
| 4 | **OpenAI** | `OPENAI_API_KEY` (+ optional `OPENAI_BASE_URL`) | any OpenAI-compatible endpoint |
| 5 | **OpenRouter** | `OPENROUTER_API_KEY` | many free models |
| 6 | **Pollinations** | *(none — keyless)* | **free, works out of the box** |
| 7 | **Heuristic** | *(always)* | offline, instant, never fails |

**You don't need any API key** — the keyless Pollinations provider gives real AI-quality study
materials for free (≈15-30 s per request; retried automatically on transient errors). Add a
`GEMINI_API_KEY` or `GROQ_API_KEY` for faster, higher-quality results:

```bash
set GEMINI_API_KEY=...        # Windows (export on macOS/Linux)
set GROQ_API_KEY=...
```

Robustness built in: malformed/truncated JSON from smaller free models is repaired, and any
missing sections (flashcards, quiz, …) are completed from the offline engine — so you **always**
get a full set of assets. Providers that fail permanently (bad key / no credits) are skipped for
the session. Toggle **"Use AI"** off in the UI (or `--no-llm` in the CLI) for instant offline output.

Tunables (env): `OMNISCRIBE_MODEL`, `GEMINI_MODEL`, `GROQ_MODEL`, `OPENROUTER_MODEL`,
`OMNISCRIBE_LLM_TIMEOUT`, `OMNISCRIBE_POLLINATIONS=0` (disable network use entirely).

---

## Testing

```bash
pip install pytest httpx
python -m pytest
```

The suite covers real OCR (synthetic + Arabic PDF), real speech transcription (synthesised
via Windows SAPI), every asset generator (English **and** Arabic), and the full FastAPI
stack including the chained pipeline and download-path security.

---

*OmniScribe v1.0 · runs locally · Tesseract OCR · Vosk speech · ReportLab assets · FastAPI*

## Licence

[MIT](LICENSE) for the code in this repo. The Amiri fonts are under the [SIL Open Font License](fonts/OFL.txt).
The full install also pulls in PyMuPDF, which is AGPL. Read [THIRD_PARTY.md](THIRD_PARTY.md) before you host or sell a copy.

Made by Amine Hammou. More tools: https://aminehammou.vercel.app/tools.html
