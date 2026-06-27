"""PDF helpers built on PyMuPDF (fitz): render pages to images and read embedded text."""
from __future__ import annotations

from typing import Iterator

import numpy as np
from PIL import Image


def open_pdf(path: str):
    import fitz  # PyMuPDF

    return fitz.open(path)


def page_count(path: str) -> int:
    doc = open_pdf(path)
    try:
        return doc.page_count
    finally:
        doc.close()


def embedded_text(path: str, page_index: int) -> str:
    """Return the text layer of a single page (empty for scanned pages)."""
    doc = open_pdf(path)
    try:
        return doc[page_index].get_text("text") or ""
    finally:
        doc.close()


def render_page(path: str, page_index: int, dpi: int = 300) -> Image.Image:
    """Render one PDF page to a PIL image at the requested DPI."""
    import fitz

    doc = open_pdf(path)
    try:
        page = doc[page_index]
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        mode = "RGB" if pix.n >= 3 else "L"
        img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        return img
    finally:
        doc.close()


def iter_pages(path: str, dpi: int = 300, page_range: tuple[int, int] | None = None) -> Iterator[tuple[int, Image.Image, str]]:
    """Yield (page_index, rendered_image, embedded_text) for each requested page.

    Opening the document once and reusing it is far faster than re-opening per page.
    """
    import fitz

    doc = open_pdf(path)
    try:
        n = doc.page_count
        start, end = (0, n) if page_range is None else (max(0, page_range[0]), min(n, page_range[1]))
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for i in range(start, end):
            page = doc[i]
            text = page.get_text("text") or ""
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            mode = "RGB" if pix.n >= 3 else "L"
            img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            yield i, img, text
    finally:
        doc.close()
