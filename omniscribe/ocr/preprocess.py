"""Image preprocessing for OCR.

Distilled from the approaches that actually worked in the source projects: grayscale +
contrast + sharpen (the "test tessraocr works" recipe) plus optional deskew/denoise from
the Arabic-OCR preprocessor. Everything is numpy/PIL only — no heavy native deps.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def to_pil(img) -> Image.Image:
    """Accept a PIL image or a numpy array, always return a PIL image."""
    if isinstance(img, Image.Image):
        return img
    if isinstance(img, np.ndarray):
        return Image.fromarray(img)
    raise TypeError(f"Unsupported image type: {type(img)}")


def _estimate_skew(gray: np.ndarray) -> float:
    """Estimate text skew angle (degrees) via the projection-profile variance method.

    Cheap and robust for document scans: rotate candidate angles, measure how 'peaky'
    the horizontal ink profile is, pick the angle with maximum variance.
    """
    # Binarise (ink = dark). Work on a downscaled copy for speed.
    small = gray
    if max(small.shape) > 1000:
        scale = 1000 / max(small.shape)
        new_size = (max(1, int(small.shape[1] * scale)), max(1, int(small.shape[0] * scale)))
        small = np.asarray(Image.fromarray(small).resize(new_size))
    binary = (small < small.mean()).astype(np.float32)
    if binary.sum() == 0:
        return 0.0

    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-5, 5.5, 0.5):
        rotated = np.asarray(
            Image.fromarray((binary * 255).astype(np.uint8)).rotate(
                angle, resample=Image.BILINEAR, fillcolor=0
            )
        )
        profile = rotated.sum(axis=1)
        score = float(np.var(profile))
        if score > best_score:
            best_score, best_angle = score, float(angle)
    return best_angle


def preprocess(
    img,
    *,
    grayscale: bool = True,
    autocontrast: bool = True,
    sharpen: bool = True,
    contrast: float = 1.6,
    denoise: bool = False,
    deskew: bool = False,
    binarize: bool = False,
) -> Image.Image:
    """Run the configurable enhancement pipeline and return a PIL image."""
    pil = to_pil(img)

    if pil.mode not in ("L", "RGB"):
        pil = pil.convert("RGB")

    if grayscale and pil.mode != "L":
        pil = pil.convert("L")

    if deskew:
        gray = np.asarray(pil if pil.mode == "L" else pil.convert("L"))
        angle = _estimate_skew(gray)
        if abs(angle) > 0.25:
            fill = 255  # white background for documents
            pil = pil.rotate(angle, resample=Image.BICUBIC, fillcolor=fill, expand=False)

    if denoise:
        pil = pil.filter(ImageFilter.MedianFilter(size=3))

    if autocontrast:
        pil = ImageOps.autocontrast(pil, cutoff=1)

    if contrast and contrast != 1.0:
        pil = ImageEnhance.Contrast(pil).enhance(contrast)

    if sharpen:
        pil = pil.filter(ImageFilter.SHARPEN)

    if binarize:
        gray = pil if pil.mode == "L" else pil.convert("L")
        arr = np.asarray(gray)
        thresh = _otsu(arr)
        pil = Image.fromarray((arr > thresh).astype(np.uint8) * 255)

    return pil


def _otsu(arr: np.ndarray) -> int:
    """Otsu's automatic threshold for binarisation."""
    hist, _ = np.histogram(arr, bins=256, range=(0, 256))
    total = arr.size
    sum_total = np.dot(np.arange(256), hist)
    sum_b = 0.0
    w_b = 0.0
    max_var = 0.0
    threshold = 127
    for i in range(256):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * hist[i]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = i
    return threshold
