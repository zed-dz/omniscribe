"""Optional Supabase persistence (history + asset storage).

Activates only when SUPABASE_URL and SUPABASE_SERVICE_KEY env vars are set, so the app
works identically with or without a database. Uses the Supabase REST + Storage HTTP APIs
directly (urllib) — no SDK, keeping the serverless bundle tiny.

Table expected (run the SQL in SUPABASE_SETUP.md):

    create table dissections (
      id uuid primary key default gen_random_uuid(),
      created_at timestamptz default now(),
      title text, language text, provider text,
      input_chars int, assets jsonb
    );

and a public Storage bucket named by SUPABASE_BUCKET (default "assets").
"""
from __future__ import annotations

import json
import mimetypes
import os
import urllib.request
from pathlib import Path


def _cfg():
    return (
        os.environ.get("SUPABASE_URL", "").rstrip("/"),
        os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY", ""),
        os.environ.get("SUPABASE_BUCKET", "assets"),
    )


def enabled() -> bool:
    url, key, _ = _cfg()
    return bool(url and key)


def _request(method: str, url: str, *, data: bytes | None, headers: dict, timeout: int = 30):
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def upload_asset(local_path: str, dest_name: str) -> str | None:
    """Upload a file to Supabase Storage; return its public URL (or None on failure)."""
    url, key, bucket = _cfg()
    if not (url and key):
        return None
    try:
        body = Path(local_path).read_bytes()
        ctype = mimetypes.guess_type(dest_name)[0] or "application/octet-stream"
        endpoint = f"{url}/storage/v1/object/{bucket}/{dest_name}"
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": ctype,
            "x-upsert": "true",
        }
        _request("POST", endpoint, data=body, headers=headers)
        return f"{url}/storage/v1/object/public/{bucket}/{dest_name}"
    except Exception:
        return None


def record_dissection(row: dict, table: str = "dissections") -> bool:
    """Insert a history row. Returns True on success, False otherwise (never raises)."""
    url, key, _ = _cfg()
    if not (url and key):
        return False
    try:
        endpoint = f"{url}/rest/v1/{table}"
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        _request("POST", endpoint, data=json.dumps(row).encode("utf-8"), headers=headers)
        return True
    except Exception:
        return False
