# Third-party parts

## In this repo

| Part | Licence | Link |
|---|---|---|
| Amiri fonts 1.002 (`fonts/`) | SIL Open Font License 1.1, see `fonts/OFL.txt` | https://github.com/aliftype/amiri |

## Installed by `requirements.txt`

| Part | Licence |
|---|---|
| FastAPI, python-multipart, uvicorn, reportlab, pypdf | MIT, Apache-2.0 or BSD |
| Pillow | MIT-CMU |
| arabic-reshaper | MIT |
| python-bidi | LGPL-3.0 |

## Added by `requirements-full.txt`

| Part | Licence |
|---|---|
| **PyMuPDF** | **AGPL-3.0, or a paid licence from Artifex** |
| pytesseract, vosk | Apache-2.0 |
| imageio-ffmpeg | BSD-2-Clause. Its wheel contains an ffmpeg program, which is GPL. |
| numpy | BSD-3-Clause and others |
| anthropic | Apache-2.0 |

The AGPL matters if you host the full app for other people or ship it inside a closed product. The slim `requirements.txt` does not use PyMuPDF.

Tesseract OCR (Apache-2.0) and the Vosk speech models (each has its own licence) are installed or downloaded by you. They are not in this repo.
