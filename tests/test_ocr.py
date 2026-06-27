import pytest

from omniscribe import capabilities
from omniscribe.ocr import OCRPipeline, postprocess, preprocess

pytestmark = pytest.mark.skipif(
    not capabilities.snapshot()["ocr"]["available"], reason="OCR engine unavailable"
)


def test_english_image_ocr(english_image):
    res = OCRPipeline().process(english_image, lang="eng", preset="fast")
    text = res.text.lower()
    assert "omniscribe" in text
    assert "hello" in text and "world" in text
    assert "2026" in text
    assert res.page_count == 1
    assert res.pages[0].source == "ocr"


def test_arabic_pdf_embedded():
    pdf = r"d:\My Drive\Finished projects - best of work\Side Quests\Arabic OCR\book.pdf"
    import os
    if not os.path.exists(pdf):
        pytest.skip("sample Arabic PDF not present")
    res = OCRPipeline().process(pdf, lang="ara", preset="fast", page_range=(0, 1))
    assert res.page_count == 1
    assert len(res.text) > 50
    # contains Arabic characters
    assert any("؀" <= ch <= "ۿ" for ch in res.text)


def test_postprocess_normalize():
    txt = "hello   world\n\n\n\n  test  "
    out = postprocess.normalize(txt)
    assert "   " not in out          # runs of spaces collapsed
    assert "\n\n\n\n" not in out     # at most 2 consecutive blank lines kept
    assert out.startswith("hello world")


def test_postprocess_stats_rtl():
    ar = "مرحبا بالعالم هذا اختبار"
    st = postprocess.stats(ar)
    assert st["is_rtl"] is True
    assert st["words"] >= 3


def test_preprocess_returns_image(english_image):
    from PIL import Image

    img = Image.open(english_image)
    out = preprocess.preprocess(img, deskew=True, denoise=True)
    assert out.size[0] > 0 and out.size[1] > 0
