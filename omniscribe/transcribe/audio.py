"""Audio conversion utilities.

Any input format (ogg/opus/mp3/m4a/flac/webm/wav) is normalised to 16 kHz mono
16-bit PCM WAV — exactly what Vosk expects — using the ffmpeg binary bundled by the
``imageio-ffmpeg`` pip package (so no system ffmpeg install is required).
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

from .. import config
from ..capabilities import ffmpeg as _ffmpeg_cap


def ffmpeg_exe() -> str:
    cap = _ffmpeg_cap()
    if not cap.get("available"):
        raise RuntimeError(cap.get("reason", "ffmpeg not available"))
    return cap["cmd"]


def _is_wav_pcm16_mono_16k(path: str) -> bool:
    try:
        with wave.open(path, "rb") as w:
            return (
                w.getnchannels() == 1
                and w.getsampwidth() == 2
                and w.getframerate() == config.TARGET_SAMPLE_RATE
            )
    except Exception:
        return False


def to_wav16k_mono(src: str | Path, dst: str | Path | None = None) -> str:
    """Return a path to a 16 kHz mono PCM WAV version of ``src``.

    If ``src`` is already in that exact format, it is returned unchanged.
    """
    src = str(src)
    if _is_wav_pcm16_mono_16k(src):
        return src

    config.ensure_dirs()
    if dst is None:
        dst = config.TMP_DIR / (Path(src).stem + "_16k.wav")
    dst = str(dst)

    cmd = [
        ffmpeg_exe(),
        "-y",
        "-i", src,
        "-ac", "1",
        "-ar", str(config.TARGET_SAMPLE_RATE),
        "-acodec", "pcm_s16le",
        "-f", "wav",
        dst,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not Path(dst).exists():
        raise RuntimeError(f"ffmpeg conversion failed:\n{proc.stderr[-1500:]}")
    return dst


def wav_duration_seconds(path: str) -> float:
    with wave.open(path, "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate() or 1
        return frames / float(rate)
