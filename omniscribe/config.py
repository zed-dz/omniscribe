"""Central configuration, paths and runtime settings for OmniScribe.

Everything that another module might need to know about *where* things live or *how*
the suite is tuned lives here, so behaviour can be changed in one place.
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- paths
# Project root = the directory that contains the ``omniscribe`` package.
PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent

# Writable working directories (created on demand by ensure_dirs()).
DATA_DIR = Path(os.environ.get("OMNISCRIBE_DATA", ROOT_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
MODEL_DIR = Path(os.environ.get("OMNISCRIBE_MODELS", ROOT_DIR / "models"))
TMP_DIR = DATA_DIR / "tmp"

ALL_DIRS = (DATA_DIR, UPLOAD_DIR, OUTPUT_DIR, MODEL_DIR, TMP_DIR)


def ensure_dirs() -> None:
    """Create every working directory if it does not yet exist."""
    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- OCR
# Tesseract executable: honour an explicit override, else the standard Windows path,
# else assume it is on PATH (Linux / mac / custom installs).
def _detect_tesseract() -> str | None:
    override = os.environ.get("TESSERACT_CMD")
    if override and Path(override).exists():
        return override
    win_default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if win_default.exists():
        return str(win_default)
    # Fall back to bare command name; pytesseract / subprocess will resolve via PATH.
    from shutil import which

    return which("tesseract")


TESSERACT_CMD = _detect_tesseract()

# Language presets the UI exposes. Keys are Tesseract language codes (joined by '+').
OCR_LANGUAGES = {
    "ara": "Arabic",
    "eng": "English",
    "fra": "French",
    "ara+eng": "Arabic + English",
    "eng+fra": "English + French",
    "ara+eng+fra": "Arabic + English + French",
}
DEFAULT_OCR_LANG = "ara+eng"

# Quality presets: (render DPI, tesseract psm, human description).
OCR_PRESETS = {
    "fast": {"dpi": 150, "psm": 6, "desc": "Quick draft (150 DPI)"},
    "balanced": {"dpi": 300, "psm": 6, "desc": "Recommended (300 DPI)"},
    "quality": {"dpi": 400, "psm": 4, "desc": "Best accuracy (400 DPI)"},
}
DEFAULT_OCR_PRESET = "balanced"

# A digital PDF page is considered to already contain a usable text layer when its
# embedded text exceeds this many characters; below it we fall back to image OCR.
DIGITAL_TEXT_THRESHOLD = 25

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}
PDF_EXTENSIONS = {".pdf"}

# --------------------------------------------------------------------------- audio
AUDIO_EXTENSIONS = {".wav", ".ogg", ".oga", ".opus", ".mp3", ".m4a", ".flac", ".aac", ".webm"}
TARGET_SAMPLE_RATE = 16000  # Vosk models expect 16 kHz mono PCM.

# Vosk models that can be auto-downloaded. Small models keep RAM/latency low (good for
# a 4-core / 8 GB machine). Larger models can be dropped into models/ manually.
VOSK_MODELS = {
    "en": {
        "name": "vosk-model-small-en-us-0.15",
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "label": "English (small, ~40 MB)",
    },
    "fr": {
        "name": "vosk-model-small-fr-0.22",
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip",
        "label": "French (small, ~41 MB)",
    },
    "ar": {
        "name": "vosk-model-ar-mgb2-0.4",
        "url": "https://alphacephei.com/vosk/models/vosk-model-ar-mgb2-0.4.zip",
        "label": "Arabic (~318 MB)",
    },
}
DEFAULT_STT_LANG = "en"

# --------------------------------------------------------------------------- dissect
# Structured learning content is extracted by a multi-provider LLM layer (see dissect/llm.py)
# with a graceful fallback chain ending in a keyless free API and then an offline heuristic.
LLM_MAX_TOKENS = int(os.environ.get("OMNISCRIBE_MAX_TOKENS", "8000"))
LLM_TIMEOUT = int(os.environ.get("OMNISCRIBE_LLM_TIMEOUT", "90"))  # seconds per provider call

# Per-provider model ids (all overridable via env).
ANTHROPIC_MODEL = os.environ.get("OMNISCRIBE_MODEL", "claude-sonnet-4-6")
ANTHROPIC_MAX_TOKENS = LLM_MAX_TOKENS  # back-compat alias
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

# Keyless free fallback (Pollinations). Set OMNISCRIBE_POLLINATIONS=0 to disable network use.
POLLINATIONS_ENABLED = os.environ.get("OMNISCRIBE_POLLINATIONS", "1") not in ("0", "false", "False")
POLLINATIONS_MODEL = os.environ.get("POLLINATIONS_MODEL", "openai")

# --------------------------------------------------------------------------- fonts
# An Arabic-capable TTF is required so generated PDFs/PNGs shape Arabic correctly.
# We search system fonts first (so local keeps its native look) and fall back to the
# bundled fonts/ dir (Amiri — covers Latin + Arabic) which ships with the repo and is the
# only option in serverless/Linux hosts without system fonts.
FONTS_DIR = ROOT_DIR / "fonts"


def _find_font(*candidates: str) -> str | None:
    search = [Path(r"C:\Windows\Fonts"), Path("/usr/share/fonts"),
              Path("/Library/Fonts"), FONTS_DIR]
    for name in candidates:
        for base in search:
            p = base / name
            if p.exists():
                return str(p)
        # also recurse one level into /usr/share/fonts/** for Linux distros
        if name and Path("/usr/share/fonts").exists():
            hits = list(Path("/usr/share/fonts").glob(f"**/{name}"))
            if hits:
                return str(hits[0])
    return None


FONT_REGULAR = _find_font("arial.ttf", "DejaVuSans.ttf", "tahoma.ttf", "Amiri-Regular.ttf") or ""
FONT_BOLD = _find_font("arialbd.ttf", "DejaVuSans-Bold.ttf", "tahomabd.ttf", "Amiri-Bold.ttf") or FONT_REGULAR
FONT_ARABIC = _find_font("tahoma.ttf", "arial.ttf", "Amiri-Regular.ttf", "DejaVuSans.ttf") or FONT_REGULAR

# --------------------------------------------------------------------------- Arabic
# Unicode normalisation map for common OCR confusions (alef/yaa/kaf variants, etc.).
ARABIC_REPLACEMENTS = {
    "ى": "ي",  # alef maksura -> yaa
    "ك": "ك",  # keheh -> kaf (keep, placeholder for clarity)
    "ک": "ك",  # keheh -> kaf
    "ی": "ي",  # farsi yeh -> arabic yeh
    "أ": "ا",  # alef hamza above -> alef (optional aggressive)
    "إ": "ا",  # alef hamza below -> alef
    "آ": "ا",  # alef madda -> alef
}
ARABIC_NUMERALS = {ord(a): str(i) for i, a in enumerate("٠١٢٣٤٥٦٧٨٩")}
ARABIC_DIACRITICS = "ًٌٍَُِّْٰٓ"

# --------------------------------------------------------------------------- web
WEB_HOST = os.environ.get("OMNISCRIBE_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("OMNISCRIBE_PORT", "8000"))
MAX_UPLOAD_MB = 200
