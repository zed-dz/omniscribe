"""Multi-format export for OCR / transcription results.

Takes a list of page-or-segment records ``[{"label": str, "text": str, ...}]`` plus the
joined text and writes TXT / JSON / CSV / Markdown / HTML (RTL-aware).
"""
from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime
from pathlib import Path


def _is_rtl(text: str) -> bool:
    arabic = len(re.findall(r"[؀-ۿ]", text))
    return arabic > max(1, len(re.sub(r"\s", "", text))) * 0.3


def export_text(text: str, out_path: str | Path) -> str:
    out_path = Path(out_path)
    out_path.write_text(text, encoding="utf-8")
    return str(out_path)


def export_json(payload: dict, out_path: str | Path) -> str:
    out_path = Path(out_path)
    payload = {**payload, "exported_at": datetime.now().isoformat(timespec="seconds")}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out_path)


def export_csv(records: list[dict], out_path: str | Path) -> str:
    out_path = Path(out_path)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["label", "text", "chars"])
        for r in records:
            t = r.get("text", "")
            writer.writerow([r.get("label", ""), t, len(t)])
    return str(out_path)


def export_markdown(records: list[dict], out_path: str | Path, title: str = "OmniScribe Output") -> str:
    out_path = Path(out_path)
    lines = [f"# {title}", "", f"_Generated {datetime.now():%Y-%m-%d %H:%M}_", ""]
    for r in records:
        lines.append(f"## {r.get('label', 'Section')}")
        lines.append("")
        lines.append(r.get("text", ""))
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return str(out_path)


def export_html(records: list[dict], out_path: str | Path, title: str = "OmniScribe Output") -> str:
    out_path = Path(out_path)
    full_text = "\n".join(r.get("text", "") for r in records)
    rtl = _is_rtl(full_text)
    direction = "rtl" if rtl else "ltr"
    align = "right" if rtl else "left"
    sections = []
    for r in records:
        body = html.escape(r.get("text", "")).replace("\n", "<br>")
        sections.append(
            f'<section><h2>{html.escape(str(r.get("label", "Section")))}</h2>'
            f'<div class="text">{body}</div></section>'
        )
    doc = f"""<!doctype html>
<html lang="{'ar' if rtl else 'en'}" dir="{direction}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: 'Segoe UI', Tahoma, 'Traditional Arabic', Arial, sans-serif;
         max-width: 860px; margin: 40px auto; padding: 0 20px; line-height: 1.9;
         color: #1f2937; background: #f9fafb; direction: {direction}; text-align: {align}; }}
  h1 {{ color: #4f46e5; }}
  h2 {{ color: #6366f1; border-bottom: 2px solid #e5e7eb; padding-bottom: 6px; }}
  .text {{ background: #fff; padding: 18px 22px; border-radius: 12px;
           box-shadow: 0 1px 3px rgba(0,0,0,.08); white-space: pre-wrap; }}
  .meta {{ color: #6b7280; font-size: .9em; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p class="meta">Generated {datetime.now():%Y-%m-%d %H:%M} · OmniScribe</p>
{''.join(sections)}
</body>
</html>"""
    out_path.write_text(doc, encoding="utf-8")
    return str(out_path)


FORMATS = {"txt", "json", "csv", "md", "html"}


def export_all(
    records: list[dict],
    text: str,
    out_dir: str | Path,
    base_name: str,
    formats: set[str] | None = None,
    title: str = "OmniScribe Output",
    extra_json: dict | None = None,
) -> dict[str, str]:
    """Write the requested formats; return {format: path}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    formats = formats or FORMATS
    written: dict[str, str] = {}
    if "txt" in formats:
        written["txt"] = export_text(text, out_dir / f"{base_name}.txt")
    if "json" in formats:
        payload = {"title": title, "records": records, "text": text}
        if extra_json:
            payload.update(extra_json)
        written["json"] = export_json(payload, out_dir / f"{base_name}.json")
    if "csv" in formats:
        written["csv"] = export_csv(records, out_dir / f"{base_name}.csv")
    if "md" in formats:
        written["md"] = export_markdown(records, out_dir / f"{base_name}.md", title)
    if "html" in formats:
        written["html"] = export_html(records, out_dir / f"{base_name}.html", title)
    return written
