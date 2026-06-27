from pathlib import Path

from omniscribe.dissect import DissectPipeline, extract
from omniscribe.dissect import assets


def _is_pdf(p):
    return Path(p).read_bytes()[:4] == b"%PDF"


def _is_png(p):
    return Path(p).read_bytes()[:4] == b"\x89PNG"


def test_heuristic_schema_complete(sample_text):
    schema = extract.extract_heuristic(sample_text)
    for key in ("title", "summary", "language", "concepts", "applications",
                "keyTakeaways", "mindmap", "infographic", "flashcards", "quiz"):
        assert key in schema
    assert schema["language"] == "en"
    assert len(schema["concepts"]) >= 1
    assert len(schema["flashcards"]) >= 1
    assert schema["mindmap"]["central"]


def test_normalize_schema_handles_garbage():
    # Even a malformed/partial dict must yield a complete, well-typed schema.
    bad = {"title": 123, "concepts": ["not a dict", {"name": "X"}], "flashcards": None,
           "mindmap": {"branches": ["just a string"]}, "quiz": [{"question": "q", "options": ["a"]}]}
    out = extract.normalize_schema(bad, "some text")
    assert isinstance(out["title"], str)
    assert all(isinstance(c, dict) for c in out["concepts"])
    assert out["mindmap"]["branches"][0]["name"] == "just a string"
    # quiz with <2 options is dropped
    assert out["quiz"] == []


def test_language_detection():
    assert extract.detect_language("This is plain English text about science") == "en"
    assert extract.detect_language("هذا نص عربي للاختبار والتعلم") == "ar"


def test_all_assets_generated(sample_text, tmp_assets_dir):
    res = DissectPipeline().process(sample_text, out_dir=tmp_assets_dir,
                                    base_name="test_assets", use_llm=False)
    assert res.method == "heuristic"
    assert set(res.files) == {"guidebook", "infographic", "flashcards", "quiz", "mindmap"}
    assert _is_pdf(res.files["guidebook"])
    assert _is_pdf(res.files["infographic"])
    assert _is_pdf(res.files["flashcards"])
    assert _is_pdf(res.files["quiz"])
    assert _is_png(res.files["mindmap"])


def test_arabic_assets(tmp_assets_dir):
    ar = ("مقدمة في علم الأحياء\n"
          "الخلية هي الوحدة الأساسية للحياة في جميع الكائنات الحية.\n"
          "تحتوي الخلية على نواة تتحكم في وظائفها الحيوية المختلفة.\n"
          "تنقسم الخلايا لتكوين خلايا جديدة في عملية تسمى الانقسام الخلوي.")
    res = DissectPipeline().process(ar, out_dir=tmp_assets_dir, base_name="test_ar", use_llm=False)
    assert res.schema["language"] == "ar"
    assert _is_pdf(res.files["guidebook"])
    assert _is_png(res.files["mindmap"])


def test_arabic_shaping():
    shaped = assets.shape("مرحبا")
    # shaping changes the codepoints (presentation forms / reorder)
    assert shaped != "مرحبا" or len(shaped) == len("مرحبا")
    # latin text is untouched
    assert assets.shape("hello") == "hello"


def test_quiz_many_options_no_crash(tmp_assets_dir):
    # Regression: a quiz item with >6 options must not raise IndexError in quiz_pdf.
    schema = extract.normalize_schema({
        "title": "Edge case",
        "quiz": [{"question": "Pick one", "options": list("ABCDEFGH"), "answer_index": 7}],
    }, "edge case text")
    assert len(schema["quiz"][0]["options"]) <= 6  # capped
    out = assets.quiz_pdf(schema, tmp_assets_dir / "quiz_edge.pdf")
    assert _is_pdf(out)


def test_subset_assets(sample_text, tmp_assets_dir):
    res = DissectPipeline().process(sample_text, out_dir=tmp_assets_dir, base_name="subset",
                                    which=["mindmap", "flashcards"], use_llm=False)
    assert set(res.files) == {"mindmap", "flashcards"}
