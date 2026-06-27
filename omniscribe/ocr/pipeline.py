"""High-level OCR orchestration.

Handles PDFs and images, automatically using a PDF's embedded text layer when present
(instant, perfect) and falling back to image OCR for scanned pages.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

from PIL import Image

from .. import config
from . import pdf, postprocess, preprocess
from .engine import get_engine

ProgressCb = Callable[[int, int, str], None] | None


@dataclass
class PageResult:
    page: int
    text: str
    source: str  # "embedded" | "ocr"
    char_count: int = 0
    seconds: float = 0.0

    def __post_init__(self):
        self.char_count = len(self.text)


@dataclass
class OCRResult:
    source_file: str
    pages: list[PageResult] = field(default_factory=list)
    lang: str = ""
    preset: str = ""
    seconds: float = 0.0
    engine: str = "tesseract"

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["text"] = self.text
        d["stats"] = postprocess.stats(self.text)
        return d


class OCRPipeline:
    def __init__(self, engine: str = "tesseract"):
        self.engine = get_engine(engine)
        self.engine_name = engine

    # ------------------------------------------------------------------ public
    def process(
        self,
        path: str,
        *,
        lang: str = config.DEFAULT_OCR_LANG,
        preset: str = config.DEFAULT_OCR_PRESET,
        page_range: tuple[int, int] | None = None,
        prefer_embedded: bool = True,
        deskew: bool = False,
        denoise: bool = False,
        remove_diacritics: bool = False,
        normalize_numbers: bool = False,
        progress: ProgressCb = None,
    ) -> OCRResult:
        path = str(path)
        ext = Path(path).suffix.lower()
        cfg = config.OCR_PRESETS.get(preset, config.OCR_PRESETS[config.DEFAULT_OCR_PRESET])
        started = time.time()

        if ext in config.PDF_EXTENSIONS:
            result = self._process_pdf(
                path, lang, cfg, page_range, prefer_embedded, deskew, denoise,
                remove_diacritics, normalize_numbers, progress,
            )
        elif ext in config.IMAGE_EXTENSIONS:
            result = self._process_image(
                path, lang, cfg, deskew, denoise, remove_diacritics, normalize_numbers, progress
            )
        else:
            raise ValueError(f"Unsupported file type for OCR: {ext}")

        result.seconds = round(time.time() - started, 2)
        result.lang = lang
        result.preset = preset
        result.engine = self.engine_name
        return result

    # ------------------------------------------------------------------ images
    def _ocr_image(self, img: Image.Image, lang: str, cfg: dict, deskew, denoise,
                   remove_diacritics, normalize_numbers) -> str:
        processed = preprocess.preprocess(
            img,
            grayscale=True,
            autocontrast=True,
            sharpen=True,
            denoise=denoise,
            deskew=deskew,
        )
        raw = self.engine.recognize(processed, lang=lang, psm=cfg["psm"])
        return postprocess.normalize(
            raw,
            fix_arabic=True,
            remove_diacritics=remove_diacritics,
            normalize_numbers=normalize_numbers,
        )

    def _process_image(self, path, lang, cfg, deskew, denoise, remove_diacritics,
                       normalize_numbers, progress) -> OCRResult:
        if progress:
            progress(0, 1, "Processing image")
        t0 = time.time()
        img = Image.open(path)
        text = self._ocr_image(img, lang, cfg, deskew, denoise, remove_diacritics, normalize_numbers)
        page = PageResult(page=1, text=text, source="ocr", seconds=round(time.time() - t0, 2))
        if progress:
            progress(1, 1, "Done")
        return OCRResult(source_file=path, pages=[page])

    # -------------------------------------------------------------------- pdfs
    def _process_pdf(self, path, lang, cfg, page_range, prefer_embedded, deskew, denoise,
                     remove_diacritics, normalize_numbers, progress) -> OCRResult:
        total = pdf.page_count(path)
        start, end = (0, total) if page_range is None else (
            max(0, page_range[0]), min(total, page_range[1])
        )
        n = end - start
        pages: list[PageResult] = []
        done = 0
        for idx, img, emb in pdf.iter_pages(path, dpi=cfg["dpi"], page_range=(start, end)):
            t0 = time.time()
            emb_clean = postprocess.normalize(
                emb, fix_arabic=True, remove_diacritics=remove_diacritics,
                normalize_numbers=normalize_numbers,
            )
            if prefer_embedded and len(emb_clean) >= config.DIGITAL_TEXT_THRESHOLD:
                pages.append(PageResult(
                    page=idx + 1, text=emb_clean, source="embedded",
                    seconds=round(time.time() - t0, 2),
                ))
            else:
                text = self._ocr_image(
                    img, lang, cfg, deskew, denoise, remove_diacritics, normalize_numbers
                )
                pages.append(PageResult(
                    page=idx + 1, text=text, source="ocr",
                    seconds=round(time.time() - t0, 2),
                ))
            done += 1
            if progress:
                progress(done, n, f"Page {idx + 1}/{total} ({pages[-1].source})")
        return OCRResult(source_file=path, pages=pages)
