"""Vosk model management — locate, download and unpack offline STT models on demand."""
from __future__ import annotations

import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .. import config

ProgressCb = Callable[[str, float], None] | None


def model_path(lang: str) -> Path | None:
    """Return the local path to an installed model for ``lang`` (or None)."""
    spec = config.VOSK_MODELS.get(lang)
    if not spec:
        return None
    p = config.MODEL_DIR / spec["name"]
    if p.exists() and any(p.iterdir()):
        return p
    # Also accept any extracted vosk model folder matching the language prefix.
    if config.MODEL_DIR.exists():
        for child in config.MODEL_DIR.iterdir():
            if child.is_dir() and child.name.startswith(f"vosk-model") and f"-{lang}-" in f"-{child.name}-":
                if (child / "conf").exists() or any(child.iterdir()):
                    return child
    return None


def is_installed(lang: str) -> bool:
    return model_path(lang) is not None


def installed_languages() -> list[str]:
    return [lang for lang in config.VOSK_MODELS if is_installed(lang)]


def download_model(lang: str, progress: ProgressCb = None) -> Path:
    """Download + unzip the Vosk model for ``lang`` into the models directory."""
    spec = config.VOSK_MODELS.get(lang)
    if not spec:
        raise ValueError(f"No model configured for language '{lang}'")

    existing = model_path(lang)
    if existing:
        return existing

    config.ensure_dirs()
    zip_path = config.MODEL_DIR / f"{spec['name']}.zip"

    def _hook(block_num, block_size, total_size):
        if progress and total_size > 0:
            pct = min(100.0, block_num * block_size * 100.0 / total_size)
            progress(f"Downloading {spec['label']}", pct)

    if progress:
        progress(f"Downloading {spec['label']}", 0.0)
    urllib.request.urlretrieve(spec["url"], zip_path, _hook)

    if progress:
        progress("Extracting model", 0.0)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(config.MODEL_DIR)
    zip_path.unlink(missing_ok=True)

    final = model_path(lang)
    if not final:
        raise RuntimeError("Model extracted but could not be located afterwards")
    if progress:
        progress("Model ready", 100.0)
    return final
