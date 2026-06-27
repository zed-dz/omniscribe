import json
from pathlib import Path

from omniscribe import export


def test_export_all_formats(tmp_assets_dir):
    records = [{"label": "Page 1", "text": "Hello world"}, {"label": "Page 2", "text": "Second page"}]
    text = "Hello world\n\nSecond page"
    files = export.export_all(records, text, tmp_assets_dir, "export_test",
                              formats={"txt", "json", "csv", "md", "html"})
    assert set(files) == {"txt", "json", "csv", "md", "html"}
    for path in files.values():
        assert Path(path).exists() and Path(path).stat().st_size > 0
    # validate JSON content
    data = json.loads(open(files["json"], encoding="utf-8").read())
    assert data["text"] == text
    assert len(data["records"]) == 2
    # html is RTL-aware: Latin text -> ltr
    html = open(files["html"], encoding="utf-8").read()
    assert 'dir="ltr"' in html


def test_export_html_rtl(tmp_assets_dir):
    records = [{"label": "ص 1", "text": "مرحبا بالعالم هذا نص عربي طويل بما يكفي"}]
    files = export.export_all(records, records[0]["text"], tmp_assets_dir, "export_rtl",
                              formats={"html"})
    html = open(files["html"], encoding="utf-8").read()
    assert 'dir="rtl"' in html
