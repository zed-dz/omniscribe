"""Shared pytest fixtures for OmniScribe."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from omniscribe import config  # noqa: E402

SAMPLE_TRANSCRIPT = (
    "Introduction to Photosynthesis\n\n"
    "Photosynthesis is the process by which green plants convert light energy into chemical energy. "
    "It takes place in the chloroplasts of plant cells. The green pigment chlorophyll absorbs sunlight.\n\n"
    "There are two main stages. The light-dependent reactions occur in the thylakoid membranes and "
    "produce ATP and NADPH. The Calvin cycle uses these products to fix carbon dioxide into glucose.\n\n"
    "Photosynthesis is essential because it produces the oxygen we breathe and forms the base of most food chains."
)


@pytest.fixture(scope="session")
def tmp_assets_dir():
    d = config.TMP_DIR / "pytest"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="session")
def english_image(tmp_assets_dir):
    """A synthetic image with known English text for OCR assertions."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1000, 260), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(config.FONT_REGULAR, 46)
    except Exception:
        font = ImageFont.load_default()
    d.text((30, 40), "OmniScribe reads text", fill="black", font=font)
    d.text((30, 120), "Hello World 2026", fill="black", font=font)
    path = tmp_assets_dir / "english_image.png"
    img.save(path)
    return str(path)


@pytest.fixture(scope="session")
def speech_wav(tmp_assets_dir):
    """A WAV of synthesized speech (Windows SAPI). Skips if unavailable."""
    path = tmp_assets_dir / "speech.wav"
    if path.exists() and path.stat().st_size > 1000:
        return str(path)
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$s.Rate=-1;"
        f"$s.SetOutputToWaveFile('{path}');"
        "$s.Speak('hello world this is a test of the transcription system');"
        "$s.Dispose()"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=60, check=True)
    except Exception as exc:  # non-Windows / no SAPI
        pytest.skip(f"cannot synthesize speech: {exc}")
    if not path.exists() or path.stat().st_size < 1000:
        pytest.skip("speech synthesis produced no audio")
    return str(path)


@pytest.fixture
def sample_text():
    return SAMPLE_TRANSCRIPT
