"""OCR engine abstraction.

A single, reliable backend (Tesseract) is implemented because the environment probe
confirmed Tesseract 5.5 with Arabic/English/French. The abstraction keeps the door open
for additional backends (EasyOCR, etc.) without touching the pipeline.
"""
from __future__ import annotations

from PIL import Image

from .. import config


class OCREngine:
    """Base interface."""

    name = "base"

    def available(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def recognize(self, image: Image.Image, lang: str, psm: int = 6) -> str:  # pragma: no cover
        raise NotImplementedError

    def recognize_data(self, image: Image.Image, lang: str, psm: int = 6) -> list[dict]:  # pragma: no cover
        raise NotImplementedError


class TesseractEngine(OCREngine):
    """Tesseract OCR via pytesseract, configured for document text."""

    name = "tesseract"

    def __init__(self):
        self._configured = False

    def _configure(self):
        if self._configured:
            return
        import pytesseract

        if config.TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
        self._pt = pytesseract
        self._configured = True

    def available(self) -> bool:
        try:
            self._configure()
            self._pt.get_tesseract_version()
            return True
        except Exception:
            return False

    def _config_str(self, psm: int) -> str:
        # OEM 3 = default LSTM+legacy engine; PSM controls page segmentation.
        return f"--oem 3 --psm {psm}"

    def recognize(self, image: Image.Image, lang: str = "eng", psm: int = 6) -> str:
        self._configure()
        return self._pt.image_to_string(image, lang=lang, config=self._config_str(psm))

    def recognize_data(self, image: Image.Image, lang: str = "eng", psm: int = 6) -> list[dict]:
        """Return word-level boxes with confidence (for highlight/overlay features)."""
        self._configure()
        data = self._pt.image_to_data(
            image, lang=lang, config=self._config_str(psm), output_type=self._pt.Output.DICT
        )
        words = []
        for i in range(len(data["text"])):
            txt = data["text"][i].strip()
            if not txt:
                continue
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = -1.0
            words.append(
                {
                    "text": txt,
                    "conf": conf,
                    "left": int(data["left"][i]),
                    "top": int(data["top"][i]),
                    "width": int(data["width"][i]),
                    "height": int(data["height"][i]),
                }
            )
        return words


def get_engine(name: str = "tesseract") -> OCREngine:
    if name == "tesseract":
        return TesseractEngine()
    raise ValueError(f"Unknown OCR engine: {name}")
