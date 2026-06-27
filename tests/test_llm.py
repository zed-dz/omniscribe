import json
import os

import pytest

from omniscribe import capabilities
from omniscribe.dissect import extract, llm


def test_pollinations_always_available():
    # The keyless provider must always be in the chain (unless explicitly disabled).
    assert "pollinations" in [p.name for p in llm._REGISTRY]
    assert "pollinations" in llm.available_providers()


def test_capabilities_reports_providers():
    cap = capabilities.llm()
    assert cap["available"] is True            # at least the keyless provider
    assert isinstance(cap["providers"], list)
    assert cap["primary"]


def test_lenient_json_trailing_comma():
    assert extract._loads_lenient('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}


def test_lenient_json_truncated():
    # Simulate a truncated model response missing closing brackets / quote.
    broken = '{"title": "X", "concepts": [{"name": "Cell", "explanation": "the basic uni'
    out = extract._loads_lenient(broken)
    assert out["title"] == "X"
    assert isinstance(out["concepts"], list)


def test_fill_gaps_completes_schema():
    # An LLM schema missing flashcards/quiz must be completed from the heuristic.
    partial = extract.normalize_schema(
        {"title": "Topic", "summary": "", "concepts": [{"name": "A", "explanation": "a"}]},
        "",
    )
    text = ("Cells are the basic unit of life. Mitochondria produce energy. "
            "DNA stores genetic information. Proteins are built from amino acids.")
    filled = extract._fill_gaps(partial, text)
    assert filled["flashcards"], "flashcards should be filled from heuristic"
    assert filled["quiz"], "quiz should be filled from heuristic"


@pytest.mark.skipif(os.environ.get("OMNISCRIBE_NO_NET") == "1", reason="network disabled")
def test_pollinations_live_extraction():
    """Real keyless extraction via Pollinations (skipped if the free service is down)."""
    text = ("Mitosis is cell division producing two identical daughter cells. "
            "It has phases: prophase, metaphase, anaphase, telophase. "
            "It is essential for growth and tissue repair in organisms.")
    try:
        raw, provider = llm.complete("Return ONLY a JSON object {\"ok\": true}.", text, max_tokens=200)
    except llm.LLMCallError:
        pytest.skip("no LLM provider reachable right now")
    assert provider in llm.available_providers() or provider
    assert raw.strip()
