"""Text post-processing — Unicode normalisation and Arabic-aware cleanup."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .. import config


def normalize(
    text: str,
    *,
    fix_arabic: bool = True,
    normalize_numbers: bool = False,
    remove_diacritics: bool = False,
    clean_whitespace: bool = True,
) -> str:
    """Normalise OCR output. Defaults are safe for any language."""
    if not text:
        return ""

    # NFKC folds compatibility forms and combines Arabic presentation forms.
    text = unicodedata.normalize("NFKC", text)

    if remove_diacritics:
        text = text.translate({ord(c): None for c in config.ARABIC_DIACRITICS})

    if fix_arabic:
        # Only apply the variant-folding map (keeps text searchable, less aggressive set).
        for src, dst in {"ى": "ي", "ک": "ك", "ی": "ي"}.items():
            text = text.replace(src, dst)

    if normalize_numbers:
        text = text.translate(config.ARABIC_NUMERALS)

    if clean_whitespace:
        text = _clean_whitespace(text)

    return text


def _clean_whitespace(text: str) -> str:
    # Collapse runs of spaces/tabs, trim each line, cap consecutive blank lines at 2.
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    out: list[str] = []
    blanks = 0
    for ln in lines:
        if ln:
            blanks = 0
            out.append(ln)
        else:
            blanks += 1
            if blanks <= 2:
                out.append("")
    return "\n".join(out).strip()


def stats(text: str) -> dict:
    """Character / word / line counts plus a quick RTL detection."""
    words = re.findall(r"\b\w+\b", text, flags=re.UNICODE)
    arabic_chars = len(re.findall(r"[؀-ۿ]", text))
    return {
        "characters": len(text),
        "characters_no_spaces": len(re.sub(r"\s", "", text)),
        "words": len(words),
        "lines": len(text.splitlines()),
        "arabic_chars": arabic_chars,
        "is_rtl": arabic_chars > max(1, len(re.sub(r"\s", "", text))) * 0.3,
    }


def word_frequency(text: str, top_n: int = 30, min_length: int = 2) -> list[tuple[str, int]]:
    words = [w for w in re.findall(r"\b\w+\b", text.lower(), flags=re.UNICODE) if len(w) >= min_length]
    return Counter(words).most_common(top_n)
