"""Runtime capability detection.

The suite is designed to degrade gracefully: every engine is optional and the UI/CLI
reports exactly what is available so a missing dependency never crashes the app.
"""
from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from . import config


def _module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


@lru_cache(maxsize=1)
def tesseract() -> dict:
    """Detect the Tesseract binary and the language data it ships with."""
    cmd = config.TESSERACT_CMD
    if not cmd or not (Path(cmd).exists() or shutil.which(cmd)):
        return {"available": False, "reason": "tesseract binary not found", "languages": []}
    try:
        ver = subprocess.run(
            [cmd, "--version"], capture_output=True, text=True, timeout=15
        )
        version_line = (ver.stdout or ver.stderr).splitlines()[0].strip()
        langs_out = subprocess.run(
            [cmd, "--list-langs"], capture_output=True, text=True, timeout=15
        )
        langs = [
            ln.strip()
            for ln in langs_out.stdout.splitlines()[1:]
            if ln.strip() and not any(c in ln for c in (" ", "/", "\\"))
        ]
        return {
            "available": True,
            "cmd": cmd,
            "version": version_line,
            "languages": sorted(langs),
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"available": False, "reason": str(exc), "languages": []}


@lru_cache(maxsize=1)
def pdf_support() -> dict:
    ok = _module_available("fitz")
    return {"available": ok, "reason": "" if ok else "PyMuPDF (fitz) not installed"}


@lru_cache(maxsize=1)
def ffmpeg() -> dict:
    """Prefer the pip-bundled imageio-ffmpeg binary, fall back to a system ffmpeg."""
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return {"available": True, "cmd": exe, "source": "imageio-ffmpeg"}
    except Exception:
        pass
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return {"available": True, "cmd": sys_ffmpeg, "source": "system"}
    return {"available": False, "reason": "no ffmpeg (pip install imageio-ffmpeg)"}


@lru_cache(maxsize=1)
def vosk() -> dict:
    ok = _module_available("vosk")
    return {"available": ok, "reason": "" if ok else "vosk not installed"}


def llm() -> dict:
    """Report the multi-provider LLM chain (not cached: env keys can change at runtime)."""
    from .dissect import llm as llm_mod

    providers = llm_mod.available_providers()
    primary = providers[0] if providers else None
    # "available" = at least one real LLM provider beyond the offline heuristic.
    return {
        "available": bool(providers),
        "providers": providers,
        "primary": primary,
        "model": {
            "gemini": config.GEMINI_MODEL,
            "anthropic": config.ANTHROPIC_MODEL,
            "groq": config.GROQ_MODEL,
            "openrouter": config.OPENROUTER_MODEL,
            "pollinations": config.POLLINATIONS_MODEL,
        }.get(primary, primary or ""),
        "reason": "" if providers else "no LLM provider reachable (offline heuristic only)",
    }


@lru_cache(maxsize=1)
def arabic_shaping() -> dict:
    ok = _module_available("arabic_reshaper") and _module_available("bidi")
    return {"available": ok}


def snapshot() -> dict:
    """Full capability report used by the API / CLI / tests."""
    tess = tesseract()
    return {
        "ocr": {
            "available": tess["available"] and pdf_support()["available"],
            "tesseract": tess,
            "pdf": pdf_support(),
        },
        "transcribe": {
            "available": vosk()["available"] and ffmpeg()["available"],
            "vosk": vosk(),
            "ffmpeg": ffmpeg(),
        },
        "dissect": {
            "available": True,  # always available via heuristic fallback
            "llm": llm(),
            "arabic_shaping": arabic_shaping(),
        },
    }


def summary_lines() -> list[str]:
    """Human-readable one-liners for CLI startup banners."""
    snap = snapshot()
    out = []
    ocr = snap["ocr"]
    out.append(
        f"OCR        : {'READY' if ocr['available'] else 'unavailable'}"
        + (f"  ({ocr['tesseract'].get('version','')}, langs: "
           f"{','.join(ocr['tesseract'].get('languages', []))})"
           if ocr["tesseract"]["available"] else "")
    )
    tr = snap["transcribe"]
    out.append(
        f"Transcribe : {'READY' if tr['available'] else 'unavailable'}"
        + ("" if tr["available"] else f"  ({tr['vosk'].get('reason') or tr['ffmpeg'].get('reason')})")
    )
    di = snap["dissect"]
    if di["llm"]["available"]:
        mode = f"LLM via {di['llm']['primary']} (+{len(di['llm']['providers'])} provider(s), heuristic fallback)"
    else:
        mode = "offline heuristic only"
    out.append(f"Dissect    : READY  ({mode})")
    return out


if __name__ == "__main__":  # pragma: no cover
    import json

    print(json.dumps(snapshot(), indent=2))
    print("\n".join(summary_lines()))
