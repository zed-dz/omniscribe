from omniscribe import capabilities


def test_snapshot_shape():
    snap = capabilities.snapshot()
    assert set(snap) == {"ocr", "transcribe", "dissect"}
    for key in snap:
        assert "available" in snap[key]


def test_dissect_always_available():
    # Dissect must always work (heuristic fallback), regardless of LLM/key state.
    assert capabilities.snapshot()["dissect"]["available"] is True


def test_summary_lines():
    lines = capabilities.summary_lines()
    assert len(lines) == 3
    assert any("OCR" in l for l in lines)
