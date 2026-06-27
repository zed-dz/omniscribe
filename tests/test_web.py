import io
import time

import pytest
from fastapi.testclient import TestClient

from omniscribe import capabilities
from omniscribe.web.app import app

client = TestClient(app)


def _poll(job_id, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/job/{job_id}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.4)
    raise AssertionError("job timed out")


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "OmniScribe" in r.text


def test_capabilities_endpoint():
    r = client.get("/api/capabilities")
    assert r.status_code == 200
    assert "ocr" in r.json()


def test_config_endpoint():
    r = client.get("/api/config")
    data = r.json()
    assert "ocr_languages" in data and "assets" in data
    assert "guidebook" in data["assets"]


def test_dissect_endpoint(sample_text):
    r = client.post("/api/dissect", data={"text": sample_text, "use_llm": "false",
                                          "assets": "guidebook,mindmap"})
    assert r.status_code == 200
    job = _poll(r.json()["job_id"])
    assert job["status"] == "done", job
    files = job["result"]["files"]
    assert "guidebook" in files and "mindmap" in files
    # downloadable
    dl = client.get(f"/download/{files['guidebook']}")
    assert dl.status_code == 200
    assert dl.content[:4] == b"%PDF"


@pytest.mark.skipif(not capabilities.snapshot()["ocr"]["available"], reason="OCR unavailable")
def test_ocr_endpoint(english_image):
    with open(english_image, "rb") as f:
        r = client.post("/api/ocr", files={"file": ("img.png", f, "image/png")},
                        data={"lang": "eng", "preset": "fast"})
    assert r.status_code == 200
    job = _poll(r.json()["job_id"])
    assert job["status"] == "done", job
    assert "hello" in job["result"]["text"].lower()


@pytest.mark.skipif(not capabilities.snapshot()["ocr"]["available"], reason="OCR unavailable")
def test_pipeline_endpoint(english_image):
    with open(english_image, "rb") as f:
        r = client.post("/api/pipeline", files={"file": ("img.png", f, "image/png")},
                        data={"ocr_lang": "eng", "ocr_preset": "fast", "use_llm": "false",
                              "assets": "mindmap,flashcards"})
    assert r.status_code == 200
    job = _poll(r.json()["job_id"])
    assert job["status"] == "done", job
    assert job["result"]["stage_kind"] == "ocr"
    assert job["result"]["dissect"]["files"]


@pytest.mark.skipif(not capabilities.snapshot()["ocr"]["available"], reason="OCR unavailable")
def test_ocr_bad_page_range(english_image):
    # Regression: malformed page_range returns a clean 400, not a 500.
    with open(english_image, "rb") as f:
        r = client.post("/api/ocr", files={"file": ("img.png", f, "image/png")},
                        data={"lang": "eng", "page_range": "abc"})
    assert r.status_code == 400


def test_download_404():
    assert client.get("/download/nonexistent_file_xyz.pdf").status_code == 404


def test_download_traversal_blocked():
    # path traversal should resolve to a bare name and 404, never escape the outputs dir
    r = client.get("/download/..%2f..%2fconfig.py")
    assert r.status_code in (404, 400)
