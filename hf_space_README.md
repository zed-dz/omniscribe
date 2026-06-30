---
title: OmniScribe
emoji: 📜
colorFrom: indigo
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Reads. Listens. Teaches. OCR + speech transcription + AI study materials.
---

# 📜 OmniScribe — Reads. Listens. Teaches.

The **full** app (this Space runs everything the serverless cloud edition can't):

- 📄 **OCR** — extract text from PDFs & images (Arabic / English / French) via Tesseract
- 🎙️ **Transcribe** — speech → text, offline, with timestamps & subtitles (Vosk)
- 🧠 **Dissect** — turn any text into a guidebook, infographic, flashcards, quiz & mindmap
- ✨ **Pipeline** — a scanned PDF or a voice note → full set of study materials

AI extraction works with **no API key** (keyless free provider) and auto-upgrades if you
set `GEMINI_API_KEY` / `GROQ_API_KEY` in the Space secrets.

Source & local install: <https://github.com/zed-dz/omniscribe>
